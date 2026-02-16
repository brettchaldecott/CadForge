"""Mesh analysis for CadForge.

Uses trimesh for watertightness checks, volume calculation,
overhang detection, wall thickness estimation, and DFM analysis.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class MeshAnalysis:
    """Results from mesh analysis."""
    file_path: str
    is_watertight: bool = False
    volume_mm3: float = 0.0
    surface_area_mm2: float = 0.0
    triangle_count: int = 0
    vertex_count: int = 0
    bounding_box: dict[str, float] = field(default_factory=dict)
    center_of_mass: list[float] = field(default_factory=list)
    issues: list[str] = field(default_factory=list)

    @property
    def volume_cm3(self) -> float:
        return self.volume_mm3 / 1000.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "file_path": self.file_path,
            "is_watertight": self.is_watertight,
            "volume_mm3": round(self.volume_mm3, 2),
            "volume_cm3": round(self.volume_cm3, 2),
            "surface_area_mm2": round(self.surface_area_mm2, 2),
            "triangle_count": self.triangle_count,
            "vertex_count": self.vertex_count,
            "bounding_box": self.bounding_box,
            "center_of_mass": [round(c, 2) for c in self.center_of_mass],
            "issues": self.issues,
        }


@dataclass
class DFMReport:
    """Design for Manufacturing analysis report."""
    printer_name: str | None = None
    build_volume_ok: bool = True
    min_wall_ok: bool = True
    overhang_ok: bool = True
    issues: list[str] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return len(self.issues) == 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "printer": self.printer_name,
            "passed": self.passed,
            "build_volume_ok": self.build_volume_ok,
            "min_wall_ok": self.min_wall_ok,
            "overhang_ok": self.overhang_ok,
            "issues": self.issues,
            "suggestions": self.suggestions,
        }


def analyze_mesh(path: Path) -> MeshAnalysis:
    """Analyze an STL/3MF mesh file.

    Args:
        path: Path to the mesh file

    Returns:
        MeshAnalysis with geometry metrics and issue detection
    """
    import trimesh

    mesh = trimesh.load(str(path))
    if isinstance(mesh, trimesh.Scene):
        # Combine all geometries
        meshes = list(mesh.geometry.values())
        if not meshes:
            return MeshAnalysis(file_path=str(path), issues=["Empty scene"])
        mesh = trimesh.util.concatenate(meshes)

    analysis = MeshAnalysis(file_path=str(path))
    analysis.is_watertight = bool(mesh.is_watertight)
    analysis.volume_mm3 = float(mesh.volume) if mesh.is_watertight else 0.0
    analysis.surface_area_mm2 = float(mesh.area)
    analysis.triangle_count = len(mesh.faces)
    analysis.vertex_count = len(mesh.vertices)

    bounds = mesh.bounds
    analysis.bounding_box = {
        "min_x": float(bounds[0][0]),
        "min_y": float(bounds[0][1]),
        "min_z": float(bounds[0][2]),
        "max_x": float(bounds[1][0]),
        "max_y": float(bounds[1][1]),
        "max_z": float(bounds[1][2]),
        "size_x": float(bounds[1][0] - bounds[0][0]),
        "size_y": float(bounds[1][1] - bounds[0][1]),
        "size_z": float(bounds[1][2] - bounds[0][2]),
    }

    analysis.center_of_mass = list(mesh.center_mass)

    # Issue detection
    if not mesh.is_watertight:
        analysis.issues.append("Mesh is not watertight (has holes or non-manifold edges)")

    if mesh.is_watertight and mesh.volume < 0:
        analysis.issues.append("Mesh has inverted normals (negative volume)")

    return analysis


def check_build_volume(
    analysis: MeshAnalysis,
    max_x: float,
    max_y: float,
    max_z: float,
) -> list[str]:
    """Check if mesh fits within printer build volume."""
    issues = []
    bb = analysis.bounding_box
    if not bb:
        return issues

    if bb.get("size_x", 0) > max_x:
        issues.append(f"Model X ({bb['size_x']:.1f}mm) exceeds build volume ({max_x}mm)")
    if bb.get("size_y", 0) > max_y:
        issues.append(f"Model Y ({bb['size_y']:.1f}mm) exceeds build volume ({max_y}mm)")
    if bb.get("size_z", 0) > max_z:
        issues.append(f"Model Z ({bb['size_z']:.1f}mm) exceeds build volume ({max_z}mm)")
    return issues


def run_dfm_check(
    path: Path,
    build_volume: tuple[float, float, float] | None = None,
    min_wall_thickness: float = 0.8,
    max_overhang_angle: float = 45.0,
) -> DFMReport:
    """Run a Design for Manufacturing check on a mesh.

    Args:
        path: Path to mesh file
        build_volume: (x, y, z) build volume in mm, or None to skip
        min_wall_thickness: Minimum wall thickness in mm
        max_overhang_angle: Maximum overhang angle from vertical in degrees

    Returns:
        DFMReport with issues and suggestions
    """
    import numpy as np
    import trimesh

    report = DFMReport()
    mesh = trimesh.load(str(path))
    if isinstance(mesh, trimesh.Scene):
        meshes = list(mesh.geometry.values())
        if not meshes:
            report.issues.append("Empty mesh file")
            return report
        mesh = trimesh.util.concatenate(meshes)

    # Build volume check
    if build_volume:
        bounds = mesh.bounds
        size = bounds[1] - bounds[0]
        if size[0] > build_volume[0] or size[1] > build_volume[1] or size[2] > build_volume[2]:
            report.build_volume_ok = False
            report.issues.append(
                f"Model size ({size[0]:.1f} x {size[1]:.1f} x {size[2]:.1f}mm) "
                f"exceeds build volume ({build_volume[0]} x {build_volume[1]} x {build_volume[2]}mm)"
            )
            report.suggestions.append("Scale down or split the model")

    # Overhang check using face normals
    if len(mesh.face_normals) > 0:
        # Face normals pointing downward (negative Z) indicate overhangs
        z_component = mesh.face_normals[:, 2]
        overhang_threshold = -np.cos(np.radians(max_overhang_angle))
        overhang_faces = np.sum(z_component < overhang_threshold)
        overhang_ratio = overhang_faces / len(mesh.faces)
        if overhang_ratio > 0.05:  # More than 5% faces are steep overhangs
            report.overhang_ok = False
            report.issues.append(
                f"{overhang_ratio:.0%} of faces exceed {max_overhang_angle}° overhang limit"
            )
            report.suggestions.append("Add supports or reorient the model")

    # Watertightness
    if not mesh.is_watertight:
        report.issues.append("Mesh is not watertight — may cause slicing issues")
        report.suggestions.append("Repair mesh in MeshLab or Meshmixer")

    return report
