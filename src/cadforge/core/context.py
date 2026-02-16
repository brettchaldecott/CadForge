"""Context window management for CadForge.

Monitors token usage and performs automatic compaction
when approaching context limits.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


# Rough token estimation: ~4 chars per token for English text
CHARS_PER_TOKEN = 4

# Default context window size (Claude Sonnet)
DEFAULT_CONTEXT_WINDOW = 200_000

# Trigger compaction at this percentage of context window
COMPACTION_THRESHOLD = 0.80


@dataclass
class ContextState:
    """Current state of the context window."""
    estimated_tokens: int = 0
    context_window: int = DEFAULT_CONTEXT_WINDOW
    compaction_count: int = 0

    @property
    def usage_ratio(self) -> float:
        return self.estimated_tokens / self.context_window if self.context_window > 0 else 0.0

    @property
    def needs_compaction(self) -> bool:
        return self.usage_ratio >= COMPACTION_THRESHOLD

    @property
    def remaining_tokens(self) -> int:
        return max(0, self.context_window - self.estimated_tokens)


def estimate_tokens(text: str) -> int:
    """Estimate token count from text length."""
    return max(1, len(text) // CHARS_PER_TOKEN)


def estimate_message_tokens(message: dict[str, Any]) -> int:
    """Estimate tokens for a single API message."""
    content = message.get("content", "")
    if isinstance(content, str):
        return estimate_tokens(content)
    elif isinstance(content, list):
        total = 0
        for block in content:
            if isinstance(block, dict):
                if "text" in block:
                    total += estimate_tokens(block["text"])
                elif "input" in block:
                    total += estimate_tokens(str(block["input"]))
            elif isinstance(block, str):
                total += estimate_tokens(block)
        return total
    return 0


def estimate_messages_tokens(messages: list[dict[str, Any]]) -> int:
    """Estimate total tokens for a list of messages."""
    return sum(estimate_message_tokens(m) for m in messages)


def compact_messages(
    messages: list[dict[str, Any]],
    summary: str,
    keep_recent: int = 4,
) -> list[dict[str, Any]]:
    """Replace old messages with a summary, keeping recent messages.

    Args:
        messages: Full message list
        summary: Generated summary of older messages
        keep_recent: Number of recent messages to preserve

    Returns:
        Compacted message list with summary + recent messages
    """
    if len(messages) <= keep_recent:
        return list(messages)

    # Build compacted list
    summary_message = {
        "role": "user",
        "content": f"[Previous conversation summary]\n\n{summary}\n\n[End of summary — conversation continues below]",
    }

    recent = messages[-keep_recent:]
    # Ensure we start with a user message for valid API format
    compacted = [summary_message]
    for msg in recent:
        compacted.append(msg)

    return compacted


def build_summary_prompt(messages: list[dict[str, Any]]) -> str:
    """Build a prompt for generating a conversation summary.

    This prompt is sent to the LLM to generate a summary of older messages.
    """
    parts = []
    for msg in messages:
        role = msg.get("role", "unknown")
        content = msg.get("content", "")
        if isinstance(content, str):
            parts.append(f"**{role}**: {content[:500]}")
        elif isinstance(content, list):
            text_parts = []
            for block in content:
                if isinstance(block, dict) and "text" in block:
                    text_parts.append(block["text"][:200])
            if text_parts:
                parts.append(f"**{role}**: {' '.join(text_parts)}")

    conversation = "\n\n".join(parts)
    return (
        "Summarize the following conversation concisely, preserving:\n"
        "- Key design decisions and parameters\n"
        "- Generated file paths and model descriptions\n"
        "- Important constraints and requirements\n"
        "- Current state of the task\n\n"
        f"Conversation:\n{conversation}"
    )
