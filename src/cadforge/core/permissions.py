"""Permission system for CadForge tool execution.

Evaluates tool calls against deny → allow → ask rule chain.
Pattern syntax: Tool(pattern) with glob-style wildcards.
"""

from __future__ import annotations

import fnmatch
import re
from dataclasses import dataclass
from enum import Enum
from typing import Any


class PermissionResult(Enum):
    """Result of permission evaluation."""
    DENY = "deny"
    ALLOW = "allow"
    ASK = "ask"


@dataclass
class ToolCall:
    """Represents a tool invocation for permission checking."""
    name: str
    argument: str = "*"

    def __str__(self) -> str:
        return f"{self.name}({self.argument})"


# Pattern: ToolName(argument_pattern)
_RULE_PATTERN = re.compile(r"^(\w+)\((.+)\)$")


def parse_rule(rule: str) -> tuple[str, str]:
    """Parse a permission rule into (tool_name, argument_pattern).

    Rules look like: Tool(pattern)
    Examples:
        ReadFile(*)          -> ("ReadFile", "*")
        Bash(rm:*)           -> ("Bash", "rm:*")
        WriteFile(**/.env)   -> ("WriteFile", "**/.env")
    """
    match = _RULE_PATTERN.match(rule.strip())
    if not match:
        raise ValueError(f"Invalid permission rule: {rule!r}. Expected format: Tool(pattern)")
    return match.group(1), match.group(2)


def matches_rule(tool_call: ToolCall, rule: str) -> bool:
    """Check if a tool call matches a permission rule.

    Uses fnmatch for glob-style pattern matching on the argument.
    The tool name must match exactly (case-sensitive).
    """
    try:
        rule_tool, rule_pattern = parse_rule(rule)
    except ValueError:
        return False

    if tool_call.name != rule_tool:
        return False

    return fnmatch.fnmatch(tool_call.argument, rule_pattern)


def evaluate_permission(
    tool_call: ToolCall,
    permissions: dict[str, list[str]],
) -> PermissionResult:
    """Evaluate a tool call against permission rules.

    Evaluation order (first match wins):
    1. deny rules → DENY (block execution)
    2. allow rules → ALLOW (auto-approve)
    3. ask rules → ASK (prompt user)
    4. No match → ASK (default to asking)
    """
    deny_rules = permissions.get("deny", [])
    allow_rules = permissions.get("allow", [])
    ask_rules = permissions.get("ask", [])

    # Check deny first
    for rule in deny_rules:
        if matches_rule(tool_call, rule):
            return PermissionResult.DENY

    # Check allow
    for rule in allow_rules:
        if matches_rule(tool_call, rule):
            return PermissionResult.ALLOW

    # Check ask
    for rule in ask_rules:
        if matches_rule(tool_call, rule):
            return PermissionResult.ASK

    # Default to ask
    return PermissionResult.ASK


def merge_permissions(
    *permission_dicts: dict[str, list[str]],
) -> dict[str, list[str]]:
    """Merge multiple permission dicts (later ones take precedence).

    For each category (deny/allow/ask), later dicts replace earlier ones entirely.
    """
    result: dict[str, list[str]] = {"deny": [], "allow": [], "ask": []}
    for perms in permission_dicts:
        for key in ("deny", "allow", "ask"):
            if key in perms:
                result[key] = list(perms[key])
    return result


def format_permission_prompt(tool_call: ToolCall) -> str:
    """Format a user-facing permission prompt for a tool call."""
    return f"Allow {tool_call.name}({tool_call.argument})? [Y/n] "
