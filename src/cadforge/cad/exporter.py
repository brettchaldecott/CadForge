"""Model export utilities for CadForge.

Supports STL, STEP, and 3MF export formats.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from cadforge.utils.paths import get_stl_output_dir, get_step_output_dir


def export_stl(
    workpiece: Any,
    name: str,
    project_root: Path,
    tolerance: float = 0.1,
    angular_tolerance: float = 0.1,
) -> Path:
    """Export a CadQuery workpiece to STL.

    Args:
        workpiece: CadQuery Workplane object
        name: Output filename (without extension)
        project_root: Project root directory
        tolerance: Linear tolerance for tessellation
        angular_tolerance: Angular tolerance for tessellation

    Returns:
        Path to the exported STL file
    """
    import cadquery as cq

    output_dir = get_stl_output_dir(project_root)
    path = output_dir / f"{name}.stl"

    cq.exporters.export(
        workpiece,
        str(path),
        exportType="STL",
        tolerance=tolerance,
        angularTolerance=angular_tolerance,
    )
    return path


def export_step(workpiece: Any, name: str, project_root: Path) -> Path:
    """Export a CadQuery workpiece to STEP.

    Args:
        workpiece: CadQuery Workplane object
        name: Output filename (without extension)
        project_root: Project root directory

    Returns:
        Path to the exported STEP file
    """
    import cadquery as cq

    output_dir = get_step_output_dir(project_root)
    path = output_dir / f"{name}.step"

    cq.exporters.export(workpiece, str(path), exportType="STEP")
    return path


def export_3mf(workpiece: Any, name: str, project_root: Path) -> Path:
    """Export a CadQuery workpiece to 3MF format.

    Falls back to STL if 3MF export is not available.

    Args:
        workpiece: CadQuery Workplane object
        name: Output filename (without extension)
        project_root: Project root directory

    Returns:
        Path to the exported file
    """
    output_dir = get_stl_output_dir(project_root)
    path = output_dir / f"{name}.3mf"

    try:
        import cadquery as cq
        cq.exporters.export(workpiece, str(path), exportType="3MF")
    except (ValueError, AttributeError):
        # 3MF not supported in this CadQuery version, fall back to STL
        path = output_dir / f"{name}.stl"
        import cadquery as cq
        cq.exporters.export(workpiece, str(path), exportType="STL")

    return path


def get_export_formats() -> list[str]:
    """Get list of supported export formats."""
    return ["stl", "step", "3mf"]
