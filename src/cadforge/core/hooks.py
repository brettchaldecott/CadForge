"""Hooks system for CadForge tool lifecycle.

Supports PreToolUse, PostToolUse, SessionStart, and UserPromptSubmit events.
Exit codes: 0=success, 2=block (stderr fed to agent), other=non-blocking error.
"""

from __future__ import annotations

import fnmatch
import re
import subprocess
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class HookEvent(Enum):
    """Lifecycle events that can trigger hooks."""
    PRE_TOOL_USE = "PreToolUse"
    POST_TOOL_USE = "PostToolUse"
    SESSION_START = "SessionStart"
    USER_PROMPT_SUBMIT = "UserPromptSubmit"


@dataclass
class HookResult:
    """Result from executing a hook."""
    exit_code: int
    stdout: str
    stderr: str

    @property
    def success(self) -> bool:
        return self.exit_code == 0

    @property
    def blocked(self) -> bool:
        return self.exit_code == 2

    @property
    def error(self) -> bool:
        return self.exit_code != 0 and self.exit_code != 2


@dataclass
class HookDefinition:
    """A single hook command definition."""
    type: str  # "command"
    command: str
    timeout: int = 30  # seconds

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> HookDefinition:
        return cls(
            type=d.get("type", "command"),
            command=d["command"],
            timeout=d.get("timeout", 30),
        )


@dataclass
class HookConfig:
    """Configuration for a hook matcher."""
    event: HookEvent
    matcher: str  # e.g., "ExecuteCadQuery(*)" or "*"
    hooks: list[HookDefinition] = field(default_factory=list)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> HookConfig:
        return cls(
            event=HookEvent(d["event"]),
            matcher=d.get("matcher", "*"),
            hooks=[HookDefinition.from_dict(h) for h in d.get("hooks", [])],
        )


# Pattern: ToolName(argument_pattern) or just *
_MATCHER_PATTERN = re.compile(r"^(\w+)\((.+)\)$")


def matches_hook(matcher: str, tool_name: str, tool_arg: str = "*") -> bool:
    """Check if a hook matcher matches a tool invocation.

    Matchers:
    - "*" matches everything
    - "ToolName(*)" matches any invocation of ToolName
    - "ToolName(pattern)" matches with glob pattern on argument
    """
    if matcher == "*":
        return True

    match = _MATCHER_PATTERN.match(matcher)
    if not match:
        return matcher == tool_name

    m_tool, m_pattern = match.group(1), match.group(2)
    if m_tool != tool_name:
        return False
    return fnmatch.fnmatch(tool_arg, m_pattern)


def execute_hook(
    hook: HookDefinition,
    env: dict[str, str] | None = None,
    cwd: str | None = None,
) -> HookResult:
    """Execute a single hook command.

    Args:
        hook: Hook definition to execute
        env: Additional environment variables (merged with os.environ)
        cwd: Working directory for the command

    Returns:
        HookResult with exit code, stdout, and stderr
    """
    import os

    full_env = dict(os.environ)
    if env:
        full_env.update(env)

    try:
        result = subprocess.run(
            hook.command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=hook.timeout,
            env=full_env,
            cwd=cwd,
        )
        return HookResult(
            exit_code=result.returncode,
            stdout=result.stdout,
            stderr=result.stderr,
        )
    except subprocess.TimeoutExpired:
        return HookResult(
            exit_code=1,
            stdout="",
            stderr=f"Hook timed out after {hook.timeout}s: {hook.command}",
        )
    except OSError as e:
        return HookResult(
            exit_code=1,
            stdout="",
            stderr=f"Hook execution failed: {e}",
        )


def get_matching_hooks(
    configs: list[HookConfig],
    event: HookEvent,
    tool_name: str = "",
    tool_arg: str = "*",
) -> list[HookDefinition]:
    """Find all hook definitions that match an event and tool invocation."""
    matching = []
    for config in configs:
        if config.event != event:
            continue
        if event in (HookEvent.PRE_TOOL_USE, HookEvent.POST_TOOL_USE):
            if not matches_hook(config.matcher, tool_name, tool_arg):
                continue
        matching.extend(config.hooks)
    return matching


def run_hooks(
    configs: list[HookConfig],
    event: HookEvent,
    tool_name: str = "",
    tool_arg: str = "*",
    env: dict[str, str] | None = None,
    cwd: str | None = None,
) -> list[HookResult]:
    """Run all matching hooks for an event.

    Returns list of results. If any hook returns exit code 2 (block),
    the caller should abort the tool execution.
    """
    hooks = get_matching_hooks(configs, event, tool_name, tool_arg)
    results = []
    for hook in hooks:
        result = execute_hook(hook, env=env, cwd=cwd)
        results.append(result)
        if result.blocked:
            break  # Stop on block
    return results


def load_hook_configs(hooks_data: list[dict[str, Any]]) -> list[HookConfig]:
    """Load hook configurations from settings data."""
    configs = []
    for entry in hooks_data:
        try:
            configs.append(HookConfig.from_dict(entry))
        except (KeyError, ValueError):
            continue  # Skip invalid configs
    return configs
