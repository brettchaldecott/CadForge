"""Event model for async agent execution.

Structured events flow from the agent through an asyncio.Queue
to the REPL renderer, decoupling generation from display.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class EventType(Enum):
    """Types of events emitted during agent execution."""

    TEXT_DELTA = "text_delta"
    TEXT_DONE = "text_done"
    TOOL_USE_START = "tool_use_start"
    TOOL_RESULT = "tool_result"
    STATUS = "status"
    ERROR = "error"
    COMPLETION = "completion"
    CANCELLED = "cancelled"


@dataclass
class AgentEvent:
    """A single event emitted by the agent during execution."""

    type: EventType
    data: dict[str, Any] = field(default_factory=dict)

    @staticmethod
    def text_delta(text: str) -> AgentEvent:
        """A chunk of streamed text."""
        return AgentEvent(type=EventType.TEXT_DELTA, data={"text": text})

    @staticmethod
    def text_done(text: str = "") -> AgentEvent:
        """End of a text content block."""
        return AgentEvent(type=EventType.TEXT_DONE, data={"text": text})

    @staticmethod
    def tool_use_start(name: str, tool_id: str) -> AgentEvent:
        """A tool_use content block has started."""
        return AgentEvent(
            type=EventType.TOOL_USE_START,
            data={"name": name, "id": tool_id},
        )

    @staticmethod
    def tool_result(name: str, tool_id: str, result: dict[str, Any]) -> AgentEvent:
        """A tool has finished executing."""
        return AgentEvent(
            type=EventType.TOOL_RESULT,
            data={"name": name, "id": tool_id, "result": result},
        )

    @staticmethod
    def status(message: str) -> AgentEvent:
        """A status update (e.g. "Thinking...", "Executing Bash...")."""
        return AgentEvent(type=EventType.STATUS, data={"message": message})

    @staticmethod
    def completion(text: str, usage: dict[str, int] | None = None) -> AgentEvent:
        """Agent has finished — final text and usage stats."""
        return AgentEvent(
            type=EventType.COMPLETION,
            data={"text": text, "usage": usage or {}},
        )

    @staticmethod
    def cancelled() -> AgentEvent:
        """Agent execution was cancelled by the user."""
        return AgentEvent(type=EventType.CANCELLED)

    @staticmethod
    def error(message: str) -> AgentEvent:
        """An error occurred during agent execution."""
        return AgentEvent(type=EventType.ERROR, data={"message": message})
