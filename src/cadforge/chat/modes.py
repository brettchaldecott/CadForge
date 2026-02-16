"""Interaction modes for CadForge REPL.

Defines agent, plan, and ask modes with their tool sets and permissions.
"""

from __future__ import annotations

from enum import Enum
from typing import FrozenSet


class InteractionMode(Enum):
    """REPL interaction modes."""

    AGENT = "agent"
    PLAN = "plan"
    ASK = "ask"

    @property
    def prompt_prefix(self) -> str:
        return f"cadforge:{self.value}> "

    @property
    def display_name(self) -> str:
        return self.value.upper()

    @property
    def color(self) -> str:
        return _MODE_COLORS[self]

    def next(self) -> InteractionMode:
        """Cycle to the next mode: agent -> plan -> ask -> agent."""
        order = [InteractionMode.AGENT, InteractionMode.PLAN, InteractionMode.ASK]
        idx = order.index(self)
        return order[(idx + 1) % len(order)]


_MODE_COLORS: dict[InteractionMode, str] = {
    InteractionMode.AGENT: "green",
    InteractionMode.PLAN: "yellow",
    InteractionMode.ASK: "cyan",
}

# Read-only tools allowed in plan mode
PLAN_MODE_TOOLS: frozenset[str] = frozenset(
    {"ReadFile", "ListFiles", "SearchVault", "Bash", "GetPrinter", "Task"}
)


def get_mode_tools(mode: InteractionMode) -> frozenset[str] | None:
    """Return the set of allowed tool names for a mode.

    Returns None for agent mode (all tools allowed),
    a frozenset for plan mode (read-only tools),
    or an empty frozenset for ask mode (no tools).
    """
    if mode == InteractionMode.AGENT:
        return None
    if mode == InteractionMode.PLAN:
        return PLAN_MODE_TOOLS
    return frozenset()


PROCEED_PHRASES: frozenset[str] = frozenset({
    "proceed", "go ahead", "do it", "execute", "implement",
    "build it", "make it", "let's go", "start", "run it",
})


def has_proceed_intent(user_input: str) -> bool:
    """Return True if the user input signals intent to execute a plan."""
    lower = user_input.lower().strip()
    return any(phrase in lower for phrase in PROCEED_PHRASES)


def get_plan_mode_permissions() -> dict[str, list[str]]:
    """Return permissions dict that denies write tools and allows read tools."""
    return {
        "deny": [
            "WriteFile(*)",
            "ExecuteCadQuery(*)",
            "ExportModel(*)",
            "AnalyzeMesh(*)",
            "ShowPreview(*)",
            "SearchWeb(*)",
        ],
        "allow": [
            "ReadFile(*)",
            "ListFiles(*)",
            "SearchVault(*)",
            "GetPrinter(*)",
            "Task(*)",
            "Bash(*)",
        ],
        "ask": [],
    }
