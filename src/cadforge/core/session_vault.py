"""Save session design logs to the vault for RAG retrieval.

After a session ends, extracts a summary of the design conversation —
what was built, decisions made, CadQuery code generated — and writes it
as a vault markdown file that can be indexed and searched.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from cadforge.utils.paths import get_session_vault_dir


def save_session_to_vault(
    project_root: Path,
    session_id: str,
    messages: list[Any],
) -> Path | None:
    """Extract a design log from session messages and save to vault.

    Only saves if the session contains meaningful design content
    (CadQuery code execution, model discussions, etc.)

    Args:
        project_root: Project root directory
        session_id: Session identifier
        messages: List of Message objects from the session

    Returns:
        Path to the vault file if saved, None if session was too short/empty.
    """
    if len(messages) < 2:
        return None

    # Extract content from messages
    user_messages = []
    assistant_messages = []
    cadquery_snippets = []
    tool_results = []

    for msg in messages:
        content = msg.content if hasattr(msg, "content") else msg.get("content", "")

        if not isinstance(content, str):
            # Tool use blocks — look for CadQuery code
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict):
                        if block.get("type") == "tool_use" and block.get("name") == "ExecuteCadQuery":
                            code = block.get("input", {}).get("code", "")
                            name = block.get("input", {}).get("output_name", "model")
                            if code:
                                cadquery_snippets.append({"name": name, "code": code})
                        elif block.get("type") == "text":
                            text = block.get("text", "")
                            if text:
                                assistant_messages.append(text)
            continue

        role = msg.role if hasattr(msg, "role") else msg.get("role", "")
        if role == "user" and isinstance(content, str):
            # Skip tool result messages (JSON arrays)
            if not content.strip().startswith("[{"):
                user_messages.append(content)
        elif role == "assistant" and isinstance(content, str):
            assistant_messages.append(content)

    # Only save if there's meaningful content
    if not user_messages and not cadquery_snippets:
        return None

    # Build the vault markdown
    md = _build_session_markdown(
        session_id=session_id,
        user_messages=user_messages,
        assistant_messages=assistant_messages,
        cadquery_snippets=cadquery_snippets,
    )

    # Write to vault
    vault_dir = get_session_vault_dir(project_root)
    vault_path = vault_dir / f"{session_id}.md"
    vault_path.write_text(md, encoding="utf-8")
    return vault_path


def _build_session_markdown(
    session_id: str,
    user_messages: list[str],
    assistant_messages: list[str],
    cadquery_snippets: list[dict[str, str]],
) -> str:
    """Build a vault-compatible markdown document from session content."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    # Build tags from content
    tags = ["session", "design-log"]
    if cadquery_snippets:
        tags.append("cadquery")

    # Extract a title from the first user message
    title = "Design Session"
    if user_messages:
        first_msg = user_messages[0][:80]
        # Clean up for title
        first_msg = first_msg.replace("\n", " ").strip()
        if first_msg:
            title = first_msg
            if len(user_messages[0]) > 80:
                title += "..."

    # Frontmatter
    lines = [
        "---",
        f"session_id: {session_id}",
        f"date: {now}",
        f"tags: [{', '.join(tags)}]",
        "---",
        "",
        f"# {title}",
        "",
    ]

    # Summary of user requests
    if user_messages:
        lines.append("## User Requests")
        lines.append("")
        for msg in user_messages[:10]:  # Cap at 10 messages
            # Truncate long messages
            text = msg[:300]
            if len(msg) > 300:
                text += "..."
            lines.append(f"- {text}")
        lines.append("")

    # Design decisions from assistant
    if assistant_messages:
        lines.append("## Design Notes")
        lines.append("")
        for msg in assistant_messages[:5]:  # Cap at 5 assistant messages
            text = msg[:500]
            if len(msg) > 500:
                text += "..."
            lines.append(text)
            lines.append("")

    # CadQuery code generated
    if cadquery_snippets:
        lines.append("## Generated CadQuery Code")
        lines.append("")
        for snippet in cadquery_snippets:
            lines.append(f"### {snippet['name']}")
            lines.append("")
            lines.append("```python")
            lines.append(snippet["code"])
            lines.append("```")
            lines.append("")

    return "\n".join(lines)
