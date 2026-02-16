"""Mesh analysis tool handler."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def handle_analyze_mesh(
    tool_input: dict[str, Any],
    project_root: Path,
) -> dict[str, Any]:
    """Analyze a mesh file for geometry metrics and issues."""
    path_str = tool_input["path"]
    path = Path(path_str) if Path(path_str).is_absolute() else project_root / path_str

    if not path.exists():
        return {"success": False, "error": f"File not found: {path}"}

    try:
        from cadforge.cad.analyzer import analyze_mesh
        analysis = analyze_mesh(path)
        return {"success": True, **analysis.to_dict()}
    except ImportError:
        return {"success": False, "error": "trimesh not installed"}
    except Exception as e:
        return {"success": False, "error": str(e)}
