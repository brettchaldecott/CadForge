"""Memory hierarchy for CadForge.

Four-tier system:
1. .cadforge/CADFORGE.local.md (personal project, gitignored)
2. CADFORGE.md (team project, version controlled)
3. ~/.cadforge/CADFORGE.md (personal global)
4. .cadforge/memory/MEMORY.md (auto-memory, agent-written)

All contents injected into system prompt at startup.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from cadforge.utils.paths import (
    get_cadforge_dir,
    get_memory_dir,
    get_user_cadforge_md,
)


MAX_AUTO_MEMORY_LINES = 200


@dataclass
class MemoryEntry:
    """A single memory source."""
    path: Path
    content: str
    tier: int  # 1=local, 2=project, 3=user, 4=auto
    label: str


@dataclass
class MemoryHierarchy:
    """Collected memory from all tiers."""
    entries: list[MemoryEntry] = field(default_factory=list)

    def get_system_prompt_content(self) -> str:
        """Build system prompt section from all memory entries."""
        if not self.entries:
            return ""
        parts = []
        for entry in sorted(self.entries, key=lambda e: e.tier):
            parts.append(f"# {entry.label}\n\n{entry.content}")
        return "\n\n---\n\n".join(parts)

    @property
    def total_lines(self) -> int:
        return sum(entry.content.count("\n") + 1 for entry in self.entries)


def _read_file(path: Path, max_lines: int | None = None) -> str | None:
    """Read file content, optionally truncating to max_lines."""
    if not path.exists():
        return None
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    if not text.strip():
        return None
    if max_lines is not None:
        lines = text.splitlines()
        if len(lines) > max_lines:
            text = "\n".join(lines[:max_lines])
            text += f"\n\n<!-- truncated at {max_lines} lines -->"
    return text


def load_memory(project_root: Path) -> MemoryHierarchy:
    """Load memory from all four tiers.

    Returns MemoryHierarchy with entries sorted by tier (highest priority first).
    """
    entries: list[MemoryEntry] = []

    # Tier 1: Personal project prefs (gitignored)
    local_md = get_cadforge_dir(project_root) / "CADFORGE.local.md"
    content = _read_file(local_md)
    if content:
        entries.append(MemoryEntry(
            path=local_md, content=content, tier=1,
            label="Personal Project Preferences",
        ))

    # Tier 2: Team project conventions
    project_md = project_root / "CADFORGE.md"
    content = _read_file(project_md)
    if content:
        entries.append(MemoryEntry(
            path=project_md, content=content, tier=2,
            label="Project Conventions",
        ))

    # Tier 3: Personal global preferences
    user_md = get_user_cadforge_md()
    if user_md:
        content = _read_file(user_md)
        if content:
            entries.append(MemoryEntry(
                path=user_md, content=content, tier=3,
                label="User Preferences",
            ))

    # Tier 4: Auto-memory (truncated)
    auto_md = get_memory_dir(project_root) / "MEMORY.md"
    content = _read_file(auto_md, max_lines=MAX_AUTO_MEMORY_LINES)
    if content:
        entries.append(MemoryEntry(
            path=auto_md, content=content, tier=4,
            label="Auto-Memory",
        ))

    return MemoryHierarchy(entries=entries)


def write_auto_memory(project_root: Path, content: str) -> Path:
    """Write content to the auto-memory MEMORY.md file."""
    memory_dir = get_memory_dir(project_root)
    path = memory_dir / "MEMORY.md"
    path.write_text(content, encoding="utf-8")
    return path


def append_auto_memory(project_root: Path, text: str) -> Path:
    """Append text to the auto-memory MEMORY.md file."""
    memory_dir = get_memory_dir(project_root)
    path = memory_dir / "MEMORY.md"
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    if existing and not existing.endswith("\n"):
        existing += "\n"
    path.write_text(existing + text + "\n", encoding="utf-8")
    return path


def write_topic_memory(project_root: Path, topic: str, content: str) -> Path:
    """Write a topic-specific memory file (e.g., debugging.md, materials.md)."""
    memory_dir = get_memory_dir(project_root)
    path = memory_dir / f"{topic}.md"
    path.write_text(content, encoding="utf-8")
    return path


def read_topic_memory(project_root: Path, topic: str) -> str | None:
    """Read a topic-specific memory file."""
    memory_dir = get_memory_dir(project_root)
    path = memory_dir / f"{topic}.md"
    return _read_file(path)


def list_topic_memories(project_root: Path) -> list[str]:
    """List available topic memory files (without .md extension)."""
    memory_dir = get_memory_dir(project_root)
    return sorted(
        p.stem for p in memory_dir.glob("*.md")
        if p.stem != "MEMORY"
    )
