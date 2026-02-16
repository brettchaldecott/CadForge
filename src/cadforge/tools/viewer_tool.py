"""3D viewer tool handler."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def handle_show_preview(
    tool_input: dict[str, Any],
    project_root: Path,
) -> dict[str, Any]:
    """Launch 3D preview of an STL file."""
    path_str = tool_input["path"]
    path = Path(path_str) if Path(path_str).is_absolute() else project_root / path_str

    if not path.exists():
        return {"success": False, "error": f"File not found: {path}"}

    try:
        from cadforge.viewer.pyvista_viewer import show_stl
        show_stl(path)
        return {"success": True, "message": f"Opened viewer for {path.name}"}
    except ImportError:
        return {"success": False, "error": "pyvista not installed"}
    except Exception as e:
        return {"success": False, "error": str(e)}
