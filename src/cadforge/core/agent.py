"""Agentic loop for CadForge.

Implements the gather → act → verify cycle using the Anthropic API
with streaming and tool use.
"""

from __future__ import annotations

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
from cadforge.core.hooks import HookConfig, HookEvent, load_hook_configs, run_hooks
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
        "SearchVault, AnalyzeMesh, ShowPreview, ExportModel, Bash, GetPrinter, SearchWeb",
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

        # Resolve authentication
        from cadforge.core.auth import resolve_auth
        self._auth_creds = resolve_auth()

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

    def process_message(self, user_input: str) -> str:
        """Process a user message through the agentic loop.

        Returns the final assistant text response.
        """
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

        # Agentic loop
        max_iterations = 20
        for _ in range(max_iterations):
            response = self._call_api(messages)

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

            # Execute tools and add results
            messages = self.session.get_api_messages()
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

            # Add tool results as user message
            self.session.add_user_message(json.dumps(tool_results))
            messages = self.session.get_api_messages()

        return "Maximum iterations reached. Please try a simpler request."

    def _call_api(self, messages: list[dict[str, Any]]) -> dict[str, Any] | None:
        """Call the Anthropic API."""
        try:
            from cadforge.core.auth import create_anthropic_client
            client, self._auth_creds = create_anthropic_client(self._auth_creds)
            response = client.messages.create(
                model=self.settings.model,
                max_tokens=self.settings.max_tokens,
                system=self.system_prompt,
                tools=get_tool_definitions(),
                messages=messages,
            )
            return {
                "content": [
                    block.model_dump() if hasattr(block, "model_dump") else block
                    for block in response.content
                ],
                "usage": {
                    "input_tokens": response.usage.input_tokens,
                    "output_tokens": response.usage.output_tokens,
                },
            }
        except ImportError:
            return {
                "content": [{"type": "text", "text": "Anthropic SDK not installed. Install with: pip install anthropic"}],
                "usage": {"input_tokens": 0, "output_tokens": 0},
            }
        except Exception as e:
            error_msg = str(e)
            if "api_key" in error_msg.lower() or "auth" in error_msg.lower():
                error_msg = (
                    f"Authentication error: {e}\n\n"
                    "CadForge supports three auth methods:\n"
                    "1. ANTHROPIC_API_KEY env var (API key billing)\n"
                    "2. ANTHROPIC_AUTH_TOKEN env var (OAuth token)\n"
                    "3. Automatic: Claude Code OAuth from macOS Keychain"
                )
            return {
                "content": [{"type": "text", "text": f"API error: {error_msg}"}],
                "usage": {"input_tokens": 0, "output_tokens": 0},
            }

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
        """Save session to the index."""
        self.session_index.update(self.session)
