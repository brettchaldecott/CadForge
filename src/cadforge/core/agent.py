"""Agentic loop for CadForge.

Implements the gather → act → verify cycle using the Anthropic API
with streaming and tool use.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any, Callable

from cadforge.config import CadForgeSettings, load_settings
from cadforge.core.context import (
    ContextState,
    build_summary_prompt,
    compact_messages,
    estimate_messages_tokens,
)
from cadforge.core.events import AgentEvent
from cadforge.core.hooks import HookConfig, HookEvent, load_hook_configs, run_hooks
from cadforge.core.llm import LLMProvider, create_provider
from cadforge.core.memory import load_memory
from cadforge.core.session import Session, SessionIndex
from cadforge.tools.executor import ToolExecutor
from cadforge.tools.registry import get_tool_definitions


def build_system_prompt(
    project_root: Path,
    settings: CadForgeSettings,
    extra_context: str = "",
) -> str:
    """Build the system prompt with memory and printer context."""
    parts = [
        "You are CadForge, an AI-powered CAD assistant for 3D printing.",
        "You help users design parametric 3D models using CadQuery,",
        "analyze meshes for manufacturability, and leverage a knowledge vault",
        "of materials, design rules, and printer profiles.",
        "",
        "When generating CadQuery code:",
        "- Assign the final workpiece to `result`",
        "- Use `cq` as the CadQuery namespace",
        "- Use `np` for numpy operations",
        "- Keep code clean and well-commented",
        "",
        "Available tools: ExecuteCadQuery, ReadFile, WriteFile, ListFiles,",
        "SearchVault, AnalyzeMesh, ShowPreview, ExportModel, Bash, GetPrinter, SearchWeb, Task",
    ]

    # Inject memory hierarchy
    memory = load_memory(project_root)
    memory_content = memory.get_system_prompt_content()
    if memory_content:
        parts.append("\n--- Project Memory ---\n")
        parts.append(memory_content)

    # Inject printer context
    if settings.printer:
        parts.append(f"\nActive printer: {settings.printer}")
        _inject_printer_context(parts, project_root, settings.printer)

    if extra_context:
        parts.append(f"\n{extra_context}")

    return "\n".join(parts)


def _inject_printer_context(parts: list[str], project_root: Path, printer_name: str) -> None:
    """Load and inject printer constraints into system prompt."""
    from cadforge.tools.project_tool import _extract_frontmatter

    printer_file = project_root / "vault" / "printers" / f"{printer_name}.md"
    if not printer_file.exists():
        return

    content = printer_file.read_text(encoding="utf-8")
    fm = _extract_frontmatter(content)
    if not fm:
        return

    bv = fm.get("build_volume", {})
    if bv:
        parts.append(
            f"Build volume: {bv.get('x', '?')} x {bv.get('y', '?')} x {bv.get('z', '?')}mm"
        )

    constraints = fm.get("constraints", {})
    if constraints:
        parts.append(f"Min wall thickness: {constraints.get('min_wall_thickness', '?')}mm")
        parts.append(f"Max overhang angle: {constraints.get('max_overhang_angle', '?')} degrees")


class Agent:
    """CadForge agent with agentic tool-use loop."""

    def __init__(
        self,
        project_root: Path,
        settings: CadForgeSettings | None = None,
        session: Session | None = None,
        ask_callback: Callable[[str], bool] | None = None,
        output_callback: Callable[[str], None] | None = None,
    ):
        self.project_root = project_root
        self.settings = settings or load_settings(project_root)
        self.session = session or Session(project_root)
        self.ask_callback = ask_callback or (lambda _: True)
        self.output_callback = output_callback or print

        # Resolve authentication and create provider
        if self.settings.provider == "ollama":
            from cadforge.core.auth import AuthCredentials
            self._auth_creds = AuthCredentials(source="ollama")
        else:
            from cadforge.core.auth import resolve_auth
            self._auth_creds = resolve_auth()

        self._provider: LLMProvider = create_provider(self.settings, self._auth_creds)
        self._async_provider = None  # Lazy-created by _get_async_provider()

        # Build system prompt
        self.system_prompt = build_system_prompt(project_root, self.settings)

        # Set up tool executor
        hook_configs = load_hook_configs(self.settings.hooks)
        self.executor = ToolExecutor(
            project_root=project_root,
            permissions=self.settings.permissions,
            hook_configs=hook_configs,
            ask_callback=self.ask_callback,
        )
        self._register_tool_handlers()

        # Context management
        self.context_state = ContextState(context_window=200_000)

        # Session index
        self.session_index = SessionIndex(project_root)

        # Run session start hooks
        run_hooks(hook_configs, HookEvent.SESSION_START, cwd=str(project_root))

    def _register_tool_handlers(self) -> None:
        """Register all built-in tool handlers."""
        from cadforge.tools.bash_tool import handle_bash
        from cadforge.tools.file_tool import (
            handle_list_files,
            handle_read_file,
            handle_write_file,
        )
        from cadforge.tools.mesh_tool import handle_analyze_mesh
        from cadforge.tools.vault_tool import handle_search_vault
        from cadforge.tools.viewer_tool import handle_show_preview
        from cadforge.tools.cadquery_tool import handle_execute_cadquery
        from cadforge.tools.project_tool import handle_get_printer
        from cadforge.tools.task_tool import handle_task

        pr = self.project_root

        self.executor.register_handler(
            "ReadFile", lambda inp: handle_read_file(inp, pr)
        )
        self.executor.register_handler(
            "WriteFile", lambda inp: handle_write_file(inp, pr)
        )
        self.executor.register_handler(
            "ListFiles", lambda inp: handle_list_files(inp, pr)
        )
        self.executor.register_handler(
            "Bash", lambda inp: handle_bash(inp, pr)
        )
        self.executor.register_handler(
            "SearchVault", lambda inp: handle_search_vault(inp, pr)
        )
        self.executor.register_handler(
            "AnalyzeMesh", lambda inp: handle_analyze_mesh(inp, pr)
        )
        self.executor.register_handler(
            "ShowPreview", lambda inp: handle_show_preview(inp, pr)
        )
        self.executor.register_handler(
            "ExecuteCadQuery", lambda inp: handle_execute_cadquery(inp, pr)
        )
        self.executor.register_handler(
            "GetPrinter",
            lambda inp: handle_get_printer(inp, pr, self.settings.printer),
        )
        self.executor.register_handler(
            "ExportModel", lambda inp: {"success": False, "error": "Not yet implemented"}
        )
        self.executor.register_handler(
            "SearchWeb", lambda inp: {"success": False, "error": "Not yet implemented"}
        )
        self.executor.register_handler(
            "Task", lambda inp: handle_task(inp, self)
        )

        # Register async handler for Task (only tool that needs native async)
        from cadforge.tools.task_tool import handle_task_async
        self.executor.register_async_handler(
            "Task", lambda inp: handle_task_async(inp, self)
        )

    def _get_async_provider(self):
        """Lazy-create the async LLM provider."""
        if self._async_provider is None:
            from cadforge.core.llm import create_async_provider
            self._async_provider = create_async_provider(self.settings, self._auth_creds)
        return self._async_provider

    def update_provider(self) -> None:
        """Hot-swap the LLM provider based on current settings."""
        if self.settings.provider == "ollama":
            from cadforge.core.auth import AuthCredentials
            self._auth_creds = AuthCredentials(source="ollama")
        else:
            from cadforge.core.auth import resolve_auth
            self._auth_creds = resolve_auth()
        self._provider = create_provider(self.settings, self._auth_creds)
        self._async_provider = None  # Reset so it's re-created on next use

    def process_message(self, user_input: str, mode: str = "agent") -> str:
        """Process a user message through the agentic loop.

        Args:
            user_input: The user's message text.
            mode: Interaction mode — "agent", "plan", or "ask".

        Returns the final assistant text response.
        """
        from cadforge.chat.modes import InteractionMode, get_mode_tools, get_plan_mode_permissions

        # Parse mode (default to agent on invalid)
        try:
            current_mode = InteractionMode(mode)
        except ValueError:
            current_mode = InteractionMode.AGENT

        # Record user message
        self.session.add_user_message(user_input)

        # Build API messages
        messages = self.session.get_api_messages()

        # Context compaction check
        tokens = estimate_messages_tokens(messages)
        self.context_state.estimated_tokens = tokens
        if self.context_state.needs_compaction and len(messages) > 8:
            summary = self._generate_summary(messages[:-4])
            messages = compact_messages(messages, summary)
            self.context_state.compaction_count += 1

        # Filter tools by mode
        all_tools = get_tool_definitions()
        allowed_tools = get_mode_tools(current_mode)
        if allowed_tools is not None:
            tools = [t for t in all_tools if t["name"] in allowed_tools]
        else:
            tools = all_tools

        # Build mode-aware system prompt
        system_prompt = self.system_prompt
        if current_mode == InteractionMode.PLAN:
            system_prompt += (
                "\n\nYou are in PLAN mode. Read-only. "
                "Provide a detailed plan, do NOT modify files or execute code. "
                "If the user asks you to proceed or execute, tell them to type "
                "/agent or press Shift+Tab to switch to agent mode."
            )
        elif current_mode == InteractionMode.ASK:
            system_prompt += (
                "\n\nYou are in ASK mode. No tools available. "
                "Answer from knowledge only."
            )

        # Swap permissions for plan mode
        original_permissions = self.executor.permissions
        if current_mode == InteractionMode.PLAN:
            self.executor.permissions = get_plan_mode_permissions()

        try:
            return self._run_agentic_loop(messages, system_prompt, tools)
        finally:
            self.executor.permissions = original_permissions

    def _run_agentic_loop(
        self,
        messages: list[dict[str, Any]],
        system_prompt: str,
        tools: list[dict[str, Any]],
    ) -> str:
        """Execute the agentic tool-use loop."""
        max_iterations = 20
        for _ in range(max_iterations):
            response = self._provider.call(
                messages, system_prompt, tools, self.settings,
            )

            if response is None:
                error_msg = "Failed to get response from API"
                self.session.add_assistant_message(error_msg)
                return error_msg

            # Process response
            text_parts = []
            tool_uses = []

            for block in response.get("content", []):
                if block.get("type") == "text":
                    text_parts.append(block["text"])
                elif block.get("type") == "tool_use":
                    tool_uses.append(block)

            # If no tool use, we're done
            if not tool_uses:
                final_text = "\n".join(text_parts)
                self.session.add_assistant_message(final_text, usage=response.get("usage"))
                return final_text

            # Record assistant message with tool uses
            self.session.add_assistant_message(
                response["content"],
                usage=response.get("usage"),
            )

            # Execute tools and collect results in Anthropic format
            tool_results = []
            for tool_use in tool_uses:
                result = self.executor.execute(
                    tool_use["name"],
                    tool_use["input"],
                )
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tool_use["id"],
                    "content": json.dumps(result),
                })

            # Add tool results as user message with proper content blocks
            self.session.add_user_message(tool_results)
            messages = self.session.get_api_messages()

        return "Maximum iterations reached. Please try a simpler request."

    async def process_message_async(
        self,
        user_input: str,
        mode: str = "agent",
        event_queue: asyncio.Queue[AgentEvent] | None = None,
    ) -> str:
        """Process a user message through the async agentic loop.

        Same logic as process_message() but uses async streaming providers
        and pushes AgentEvents to the queue for real-time rendering.

        Raises asyncio.CancelledError if the task is cancelled.
        """
        from cadforge.chat.modes import InteractionMode, get_mode_tools, get_plan_mode_permissions

        if event_queue is None:
            event_queue = asyncio.Queue()

        try:
            current_mode = InteractionMode(mode)
        except ValueError:
            current_mode = InteractionMode.AGENT

        self.session.add_user_message(user_input)
        messages = self.session.get_api_messages()

        tokens = estimate_messages_tokens(messages)
        self.context_state.estimated_tokens = tokens
        if self.context_state.needs_compaction and len(messages) > 8:
            summary = self._generate_summary(messages[:-4])
            messages = compact_messages(messages, summary)
            self.context_state.compaction_count += 1

        all_tools = get_tool_definitions()
        allowed_tools = get_mode_tools(current_mode)
        if allowed_tools is not None:
            tools = [t for t in all_tools if t["name"] in allowed_tools]
        else:
            tools = all_tools

        system_prompt = self.system_prompt
        if current_mode == InteractionMode.PLAN:
            system_prompt += (
                "\n\nYou are in PLAN mode. Read-only. "
                "Provide a detailed plan, do NOT modify files or execute code. "
                "If the user asks you to proceed or execute, tell them to type "
                "/agent or press Shift+Tab to switch to agent mode."
            )
        elif current_mode == InteractionMode.ASK:
            system_prompt += (
                "\n\nYou are in ASK mode. No tools available. "
                "Answer from knowledge only."
            )

        original_permissions = self.executor.permissions
        if current_mode == InteractionMode.PLAN:
            self.executor.permissions = get_plan_mode_permissions()

        try:
            return await self._run_agentic_loop_async(
                messages, system_prompt, tools, event_queue
            )
        except asyncio.CancelledError:
            await event_queue.put(AgentEvent.cancelled())
            raise
        finally:
            self.executor.permissions = original_permissions

    async def _run_agentic_loop_async(
        self,
        messages: list[dict[str, Any]],
        system_prompt: str,
        tools: list[dict[str, Any]],
        event_queue: asyncio.Queue[AgentEvent],
    ) -> str:
        """Execute the async agentic tool-use loop with streaming."""
        provider = self._get_async_provider()
        max_iterations = 20

        for _ in range(max_iterations):
            await event_queue.put(AgentEvent.status("Thinking..."))

            response = await provider.stream(
                messages, system_prompt, tools, self.settings, event_queue
            )

            if response is None:
                error_msg = "Failed to get response from API"
                self.session.add_assistant_message(error_msg)
                await event_queue.put(AgentEvent.error(error_msg))
                return error_msg

            text_parts = []
            tool_uses = []

            for block in response.get("content", []):
                if block.get("type") == "text":
                    text_parts.append(block["text"])
                elif block.get("type") == "tool_use":
                    tool_uses.append(block)

            if not tool_uses:
                final_text = "\n".join(text_parts)
                self.session.add_assistant_message(final_text, usage=response.get("usage"))
                await event_queue.put(
                    AgentEvent.completion(final_text, response.get("usage"))
                )
                return final_text

            # Record assistant message with tool uses
            self.session.add_assistant_message(
                response["content"],
                usage=response.get("usage"),
            )

            # Execute tools
            tool_results = []
            for tool_use in tool_uses:
                name = tool_use["name"]
                await event_queue.put(AgentEvent.status(f"Executing {name}..."))

                result = await self.executor.execute_async(
                    name, tool_use["input"],
                )

                await event_queue.put(
                    AgentEvent.tool_result(name, tool_use["id"], result)
                )

                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tool_use["id"],
                    "content": json.dumps(result),
                })

            self.session.add_user_message(tool_results)
            messages = self.session.get_api_messages()

        return "Maximum iterations reached. Please try a simpler request."

    def _generate_summary(self, messages: list[dict[str, Any]]) -> str:
        """Generate a conversation summary for context compaction."""
        prompt = build_summary_prompt(messages)
        # For simplicity, create a basic summary without API call
        parts = []
        for msg in messages[-6:]:
            content = msg.get("content", "")
            if isinstance(content, str) and content.strip():
                parts.append(content[:200])
        return "Previous conversation covered: " + "; ".join(parts)

    def save_session(self) -> None:
        """Save session to the index and export design log to vault."""
        self.session_index.update(self.session)

        # Export session design log to vault for RAG retrieval
        from cadforge.core.session_vault import save_session_to_vault
        save_session_to_vault(
            self.project_root,
            self.session.session_id,
            self.session.messages,
        )
