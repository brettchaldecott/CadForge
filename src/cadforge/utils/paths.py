"""Project path helpers for CadForge."""

from __future__ import annotations

import os
from pathlib import Path


def find_project_root(start: Path | None = None) -> Path | None:
    """Walk up from start directory to find project root.

    Project root is identified by the presence of CADFORGE.md
    or .cadforge/ directory.
    """
    current = (start or Path.cwd()).resolve()
    for directory in [current, *current.parents]:
        if (directory / "CADFORGE.md").exists():
            return directory
        if (directory / ".cadforge").is_dir():
            return directory
    return None


def get_project_root(start: Path | None = None) -> Path:
    """Get project root, raising if not found."""
    root = find_project_root(start)
    if root is None:
        raise FileNotFoundError(
            "No CadForge project found. Run 'cadforge init' to create one."
        )
    return root


def get_cadforge_dir(project_root: Path) -> Path:
    """Get .cadforge/ directory, creating if needed."""
    d = project_root / ".cadforge"
    d.mkdir(exist_ok=True)
    return d


def get_memory_dir(project_root: Path) -> Path:
    """Get .cadforge/memory/ directory, creating if needed."""
    d = get_cadforge_dir(project_root) / "memory"
    d.mkdir(exist_ok=True)
    return d


def get_output_dir(project_root: Path) -> Path:
    """Get output/ directory, creating if needed."""
    d = project_root / "output"
    d.mkdir(exist_ok=True)
    return d


def get_stl_output_dir(project_root: Path) -> Path:
    """Get output/stl/ directory, creating if needed."""
    d = get_output_dir(project_root) / "stl"
    d.mkdir(exist_ok=True)
    return d


def get_step_output_dir(project_root: Path) -> Path:
    """Get output/step/ directory, creating if needed."""
    d = get_output_dir(project_root) / "step"
    d.mkdir(exist_ok=True)
    return d


def get_vault_dir(project_root: Path) -> Path:
    """Get vault/ directory path."""
    return project_root / "vault"


def get_lance_dir(project_root: Path) -> Path:
    """Get .lance/ directory, creating if needed."""
    d = project_root / ".lance"
    d.mkdir(exist_ok=True)
    return d


def get_sessions_dir() -> Path:
    """Get user-level sessions directory."""
    d = Path.home() / ".cadforge" / "sessions"
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_project_sessions_dir(project_root: Path) -> Path:
    """Get project-specific sessions directory under user home."""
    encoded = str(project_root).replace("/", "-").replace("\\", "-").strip("-")
    d = Path.home() / ".cadforge" / "projects" / encoded
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_user_settings_path() -> Path:
    """Get user-level settings.json path."""
    return Path.home() / ".cadforge" / "settings.json"


def get_project_settings_path(project_root: Path) -> Path:
    """Get project-level settings.json path."""
    return project_root / ".cadforge" / "settings.json"


def get_user_cadforge_md() -> Path | None:
    """Get user-level CADFORGE.md if it exists."""
    p = Path.home() / ".cadforge" / "CADFORGE.md"
    return p if p.exists() else None


def get_skills_dirs(project_root: Path) -> list[Path]:
    """Get skill directories in precedence order (workspace > user > bundled)."""
    dirs = []
    workspace = project_root / "skills"
    if workspace.is_dir():
        dirs.append(workspace)
    user = Path.home() / ".cadforge" / "skills"
    if user.is_dir():
        dirs.append(user)
    bundled = Path(__file__).parent.parent / "skills" / "builtin"
    if bundled.is_dir():
        dirs.append(bundled)
    return dirs
