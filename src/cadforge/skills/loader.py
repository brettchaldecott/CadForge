"""Skill loader for CadForge.

Discovers and loads SKILL.md files from workspace, user, and bundled directories.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from cadforge.utils.paths import get_skills_dirs


@dataclass
class Skill:
    """A loaded skill definition."""
    name: str
    description: str
    allowed_tools: list[str]
    prompt: str
    source_path: Path
    priority: int  # Lower = higher priority (0=workspace, 1=user, 2=bundled)

    @property
    def slash_command(self) -> str:
        return f"/{self.name}"


def load_skill(skill_dir: Path, priority: int = 0) -> Skill | None:
    """Load a skill from a directory containing SKILL.md.

    Args:
        skill_dir: Directory containing SKILL.md
        priority: Priority level (0=workspace, 1=user, 2=bundled)

    Returns:
        Skill object or None if invalid
    """
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.exists():
        return None

    content = skill_md.read_text(encoding="utf-8")
    frontmatter, body = _extract_frontmatter(content)

    name = frontmatter.get("name", skill_dir.name)
    description = frontmatter.get("description", "")
    tools_str = frontmatter.get("allowed-tools", "")
    allowed_tools = [t.strip() for t in tools_str.split(",") if t.strip()]

    return Skill(
        name=name,
        description=description,
        allowed_tools=allowed_tools,
        prompt=body.strip(),
        source_path=skill_md,
        priority=priority,
    )


def discover_skills(project_root: Path) -> list[Skill]:
    """Discover all available skills from all directories.

    Returns skills sorted by priority (workspace > user > bundled).
    Skills with the same name are deduplicated (highest priority wins).
    """
    skills_dirs = get_skills_dirs(project_root)
    all_skills: dict[str, Skill] = {}

    for priority, skills_dir in enumerate(skills_dirs):
        for entry in sorted(skills_dir.iterdir()):
            if entry.is_dir() and (entry / "SKILL.md").exists():
                skill = load_skill(entry, priority=priority)
                if skill and skill.name not in all_skills:
                    all_skills[skill.name] = skill

    return sorted(all_skills.values(), key=lambda s: (s.priority, s.name))


def get_skill_by_name(project_root: Path, name: str) -> Skill | None:
    """Find a skill by name."""
    for skill in discover_skills(project_root):
        if skill.name == name:
            return skill
    return None


def get_slash_commands(project_root: Path) -> dict[str, Skill]:
    """Get all available slash commands."""
    return {skill.slash_command: skill for skill in discover_skills(project_root)}


def _extract_frontmatter(content: str) -> tuple[dict[str, Any], str]:
    """Extract YAML frontmatter from skill content."""
    if not content.startswith("---"):
        return {}, content
    parts = content.split("---", 2)
    if len(parts) < 3:
        return {}, content
    try:
        fm = yaml.safe_load(parts[1]) or {}
    except yaml.YAMLError:
        fm = {}
    return fm, parts[2]
