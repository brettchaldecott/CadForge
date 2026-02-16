"""File operation tool handlers — read, write, list, search."""

from __future__ import annotations

import fnmatch
from pathlib import Path
from typing import Any


def handle_read_file(tool_input: dict[str, Any], project_root: Path) -> dict[str, Any]:
    """Read file contents."""
    path = _resolve_path(tool_input["path"], project_root)
    if not path.exists():
        return {"success": False, "error": f"File not found: {path}"}
    if not path.is_file():
        return {"success": False, "error": f"Not a file: {path}"}
    try:
        content = path.read_text(encoding="utf-8")
        return {"success": True, "content": content, "path": str(path)}
    except Exception as e:
        return {"success": False, "error": str(e)}


def handle_write_file(tool_input: dict[str, Any], project_root: Path) -> dict[str, Any]:
    """Write content to a file."""
    path = _resolve_path(tool_input["path"], project_root)
    content = tool_input["content"]
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return {"success": True, "path": str(path), "bytes_written": len(content)}
    except Exception as e:
        return {"success": False, "error": str(e)}


def handle_list_files(tool_input: dict[str, Any], project_root: Path) -> dict[str, Any]:
    """List files matching a glob pattern."""
    pattern = tool_input.get("pattern", "*")
    base = _resolve_path(tool_input.get("path", "."), project_root)
    if not base.is_dir():
        return {"success": False, "error": f"Not a directory: {base}"}
    try:
        matches = sorted(str(p.relative_to(project_root)) for p in base.rglob(pattern))
        return {"success": True, "files": matches[:200], "total": len(matches)}
    except Exception as e:
        return {"success": False, "error": str(e)}


def _resolve_path(path_str: str, project_root: Path) -> Path:
    """Resolve a path relative to the project root."""
    p = Path(path_str)
    if p.is_absolute():
        return p
    return project_root / p
