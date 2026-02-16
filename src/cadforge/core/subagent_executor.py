"""Sub-agent executor for CadForge.

Runs a mini agentic loop with a restricted tool set.
Sub-agents cannot spawn other sub-agents (no nesting).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from cadforge.config import CadForgeSettings
from cadforge.core.llm import LLMProvider
from cadforge.core.subagent import SubagentConfig, SubagentResult
from cadforge.tools.executor import ToolExecutor
from cadforge.tools.registry import get_tool_definitions


def _filter_tools(
    allowed_names: list[str],
) -> list[dict[str, Any]]:
    """Filter tool definitions to only those in allowed_names.

    Always excludes the Task tool to prevent sub-agent nesting.
    """
    allowed = set(allowed_names) - {"Task"}
    return [t for t in get_tool_definitions() if t["name"] in allowed]


def _create_tool_handlers(
    tools: list[str],
    project_root: Path,
    settings: CadForgeSettings,
) -> dict[str, Callable]:
    """Create handler functions for the allowed tools.

    Reuses the same handler implementations as the main agent.
    """
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

    pr = project_root
    all_handlers: dict[str, Callable] = {
        "ReadFile": lambda inp: handle_read_file(inp, pr),
        "WriteFile": lambda inp: handle_write_file(inp, pr),
        "ListFiles": lambda inp: handle_list_files(inp, pr),
        "Bash": lambda inp: handle_bash(inp, pr),
        "SearchVault": lambda inp: handle_search_vault(inp, pr),
        "AnalyzeMesh": lambda inp: handle_analyze_mesh(inp, pr),
        "ShowPreview": lambda inp: handle_show_preview(inp, pr),
        "ExecuteCadQuery": lambda inp: handle_execute_cadquery(inp, pr),
        "GetPrinter": lambda inp: handle_get_printer(inp, pr, settings.printer),
        "ExportModel": lambda inp: {"success": False, "error": "Not yet implemented"},
        "SearchWeb": lambda inp: {"success": False, "error": "Not yet implemented"},
    }

    allowed = set(tools) - {"Task"}
    return {name: handler for name, handler in all_handlers.items() if name in allowed}


def run_subagent(
    config: SubagentConfig,
    task_prompt: str,
    context: str,
    provider: LLMProvider,
    settings: CadForgeSettings,
    project_root: Path,
    permissions: dict[str, list[str]],
    ask_callback: Callable[[str], bool],
) -> SubagentResult:
    """Run a sub-agent with a restricted tool set.

    Executes a mini agentic loop: call the LLM, execute any tool_use
    blocks, feed results back, repeat until the LLM returns text only
    or max_iterations is reached.

    Args:
        config: Sub-agent configuration (tools, model, system prompt, etc.)
        task_prompt: The task to accomplish
        context: Optional additional context
        provider: LLM provider to use for API calls
        settings: Parent CadForge settings
        project_root: Project root directory
        permissions: Permission rules for tool execution
        ask_callback: Callback for permission prompts

    Returns:
        SubagentResult with output text and success status
    """
    # Build filtered tool definitions (excludes Task)
    filtered_tools = _filter_tools(config.tools)

    # Create a restricted tool executor
    handlers = _create_tool_handlers(config.tools, project_root, settings)
    sub_executor = ToolExecutor(
        project_root=project_root,
        permissions=permissions,
        ask_callback=ask_callback,
    )
    for name, handler in handlers.items():
        sub_executor.register_handler(name, handler)

    # Override model in settings for the sub-agent
    sub_settings = CadForgeSettings(
        permissions=settings.permissions,
        hooks=settings.hooks,
        provider=settings.provider,
        model=config.model,
        max_tokens=settings.max_tokens,
        temperature=settings.temperature,
        printer=settings.printer,
        base_url=settings.base_url,
    )

    # Build initial messages
    user_content = task_prompt
    if context:
        user_content = f"{context}\n\n{task_prompt}"

    messages: list[dict[str, Any]] = [
        {"role": "user", "content": user_content},
    ]

    # Mini agentic loop
    collected_text: list[str] = []
    for _ in range(config.max_iterations):
        response = provider.call(
            messages, config.system_prompt, filtered_tools, sub_settings,
        )

        if response is None:
            return SubagentResult(
                agent_name=config.name,
                success=False,
                output="",
                error="Failed to get response from LLM provider",
            )

        # Parse response blocks
        text_parts: list[str] = []
        tool_uses: list[dict[str, Any]] = []

        for block in response.get("content", []):
            if block.get("type") == "text":
                text_parts.append(block["text"])
            elif block.get("type") == "tool_use":
                tool_uses.append(block)

        # If no tool use, we're done
        if not tool_uses:
            collected_text.extend(text_parts)
            return SubagentResult(
                agent_name=config.name,
                success=True,
                output="\n".join(collected_text),
            )

        # Collect any text alongside tool use
        collected_text.extend(text_parts)

        # Record assistant response
        messages.append({"role": "assistant", "content": response["content"]})

        # Execute each tool and collect results
        tool_results: list[dict[str, Any]] = []
        for tool_use in tool_uses:
            result = sub_executor.execute(tool_use["name"], tool_use["input"])
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": tool_use["id"],
                "content": json.dumps(result),
            })

        # Add tool results as user message
        messages.append({"role": "user", "content": tool_results})

    # Max iterations reached — return partial output
    warning = f"\n[Sub-agent '{config.name}' reached max iterations ({config.max_iterations})]"
    collected_text.append(warning)
    return SubagentResult(
        agent_name=config.name,
        success=True,
        output="\n".join(collected_text),
    )
