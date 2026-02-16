"""Permission-gated tool executor for CadForge.

Dispatches tool calls through the permission system and hooks,
then executes the appropriate tool handler.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Callable, Coroutine

from cadforge.core.hooks import (
    HookConfig,
    HookEvent,
    load_hook_configs,
    run_hooks,
)
from cadforge.core.permissions import (
    PermissionResult,
    ToolCall,
    evaluate_permission,
)


class ToolExecutor:
    """Executes tools with permission checking and hook lifecycle."""

    def __init__(
        self,
        project_root: Path,
        permissions: dict[str, list[str]],
        hook_configs: list[HookConfig] | None = None,
        ask_callback: Callable[[str], bool] | None = None,
    ):
        self.project_root = project_root
        self.permissions = permissions
        self.hook_configs = hook_configs or []
        self.ask_callback = ask_callback or (lambda _: True)
        self._handlers: dict[str, Callable] = {}
        self._async_handlers: dict[str, Callable[..., Coroutine]] = {}

    def register_handler(self, tool_name: str, handler: Callable) -> None:
        """Register a handler function for a tool."""
        self._handlers[tool_name] = handler

    def register_async_handler(
        self, tool_name: str, handler: Callable[..., Coroutine]
    ) -> None:
        """Register an async handler for a tool.

        Async handlers are preferred by execute_async(). Tools without
        an async handler fall back to running the sync handler in a thread.
        """
        self._async_handlers[tool_name] = handler

    def execute(
        self,
        tool_name: str,
        tool_input: dict[str, Any],
    ) -> dict[str, Any]:
        """Execute a tool with permission checking and hooks.

        Returns dict with:
        - success: bool
        - result: Any (tool output)
        - error: str | None
        - blocked: bool (True if denied by permissions or hooks)
        """
        # Build tool call for permission checking
        arg = _extract_permission_arg(tool_name, tool_input)
        tool_call = ToolCall(name=tool_name, argument=arg)

        # Check permissions
        perm = evaluate_permission(tool_call, self.permissions)
        if perm == PermissionResult.DENY:
            return {
                "success": False,
                "result": None,
                "error": f"Permission denied: {tool_call}",
                "blocked": True,
            }

        if perm == PermissionResult.ASK:
            from cadforge.core.permissions import format_permission_prompt
            prompt = format_permission_prompt(tool_call)
            if not self.ask_callback(prompt):
                return {
                    "success": False,
                    "result": None,
                    "error": f"User denied: {tool_call}",
                    "blocked": True,
                }

        # Run PreToolUse hooks
        pre_results = run_hooks(
            self.hook_configs,
            HookEvent.PRE_TOOL_USE,
            tool_name,
            arg,
            cwd=str(self.project_root),
        )
        for hr in pre_results:
            if hr.blocked:
                return {
                    "success": False,
                    "result": None,
                    "error": f"Blocked by hook: {hr.stderr}",
                    "blocked": True,
                }

        # Execute tool handler
        handler = self._handlers.get(tool_name)
        if handler is None:
            return {
                "success": False,
                "result": None,
                "error": f"No handler registered for tool: {tool_name}",
                "blocked": False,
            }

        try:
            result = handler(tool_input)
            output = {
                "success": True,
                "result": result,
                "error": None,
                "blocked": False,
            }
        except Exception as e:
            output = {
                "success": False,
                "result": None,
                "error": str(e),
                "blocked": False,
            }

        # Run PostToolUse hooks
        run_hooks(
            self.hook_configs,
            HookEvent.POST_TOOL_USE,
            tool_name,
            arg,
            env={"TOOL_OUTPUT": str(output.get("result", ""))},
            cwd=str(self.project_root),
        )

        return output

    async def execute_async(
        self,
        tool_name: str,
        tool_input: dict[str, Any],
    ) -> dict[str, Any]:
        """Execute a tool asynchronously.

        If a native async handler is registered, calls it directly.
        Otherwise wraps the sync handler via asyncio.to_thread().
        Permission checks and hooks run in a thread pool since they
        are synchronous.
        """
        # Run permission + hook checks in a thread (they're sync)
        check_result = await asyncio.to_thread(
            self._check_permissions, tool_name, tool_input
        )
        if check_result is not None:
            return check_result

        # Prefer native async handler
        if tool_name in self._async_handlers:
            try:
                result = await self._async_handlers[tool_name](tool_input)
                output = {
                    "success": True,
                    "result": result,
                    "error": None,
                    "blocked": False,
                }
            except Exception as e:
                output = {
                    "success": False,
                    "result": None,
                    "error": str(e),
                    "blocked": False,
                }
        else:
            # Fall back to sync handler in thread pool
            output = await asyncio.to_thread(self.execute, tool_name, tool_input)

        return output

    def _check_permissions(
        self,
        tool_name: str,
        tool_input: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Check permissions and run pre-hooks. Returns a result dict if blocked, else None."""
        arg = _extract_permission_arg(tool_name, tool_input)
        tool_call = ToolCall(name=tool_name, argument=arg)

        perm = evaluate_permission(tool_call, self.permissions)
        if perm == PermissionResult.DENY:
            return {
                "success": False,
                "result": None,
                "error": f"Permission denied: {tool_call}",
                "blocked": True,
            }

        if perm == PermissionResult.ASK:
            from cadforge.core.permissions import format_permission_prompt
            prompt = format_permission_prompt(tool_call)
            if not self.ask_callback(prompt):
                return {
                    "success": False,
                    "result": None,
                    "error": f"User denied: {tool_call}",
                    "blocked": True,
                }

        pre_results = run_hooks(
            self.hook_configs,
            HookEvent.PRE_TOOL_USE,
            tool_name,
            arg,
            cwd=str(self.project_root),
        )
        for hr in pre_results:
            if hr.blocked:
                return {
                    "success": False,
                    "result": None,
                    "error": f"Blocked by hook: {hr.stderr}",
                    "blocked": True,
                }

        return None


def _extract_permission_arg(tool_name: str, tool_input: dict[str, Any]) -> str:
    """Extract the primary argument for permission matching."""
    if tool_name == "Bash":
        cmd = tool_input.get("command", "")
        # Extract first word as prefix for matching (e.g., "rm:file.txt")
        parts = cmd.split(None, 1)
        return f"{parts[0]}:{parts[1]}" if len(parts) > 1 else parts[0] if parts else "*"
    elif tool_name in ("ReadFile", "WriteFile", "AnalyzeMesh", "ShowPreview"):
        return tool_input.get("path", "*")
    elif tool_name == "ExecuteCadQuery":
        return tool_input.get("output_name", "*")
    elif tool_name == "SearchVault":
        return tool_input.get("query", "*")
    elif tool_name == "ExportModel":
        return tool_input.get("source", "*")
    elif tool_name == "ListFiles":
        return tool_input.get("pattern", "*")
    elif tool_name == "Task":
        return tool_input.get("agent_type", "*")
    return "*"
