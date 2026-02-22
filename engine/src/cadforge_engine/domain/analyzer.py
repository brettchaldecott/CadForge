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
    thin_wall_count: int = 0
    thin_wall_samples: int = 0
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
            "thin_wall_count": self.thin_wall_count,
            "thin_wall_samples": self.thin_wall_samples,
            "issues": self.issues,
            "suggestions": self.suggestions,
        }


@dataclass
class GeometricDiff:
    """Comparison between two meshes."""
    volume_delta_mm3: float = 0.0
    volume_delta_pct: float = 0.0
    surface_area_delta_mm2: float = 0.0
    bbox_size_delta: dict[str, float] = field(default_factory=dict)
    center_of_mass_delta: list[float] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "volume_delta_mm3": round(self.volume_delta_mm3, 2),
            "volume_delta_pct": round(self.volume_delta_pct, 2),
            "surface_area_delta_mm2": round(self.surface_area_delta_mm2, 2),
            "bbox_size_delta": {k: round(v, 2) for k, v in self.bbox_size_delta.items()},
            "center_of_mass_delta": [round(c, 2) for c in self.center_of_mass_delta],
        }


@dataclass
class AlgorithmicFidelityResult:
    """Algorithmic fidelity scoring result (no LLM needed)."""
    dimension_match_score: float = 0.0    # 0-100
    volume_sanity_score: float = 0.0      # 0-100
    dfm_score: float = 0.0               # 0-100
    overall_score: float = 0.0           # 0-100 weighted
    dimension_details: dict[str, float] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "dimension_match_score": round(self.dimension_match_score, 2),
            "volume_sanity_score": round(self.volume_sanity_score, 2),
            "dfm_score": round(self.dfm_score, 2),
            "overall_score": round(self.overall_score, 2),
            "dimension_details": {k: round(v, 2) for k, v in self.dimension_details.items()},
            "notes": self.notes,
        }


@dataclass
class FEAStubResult:
    """Lightweight structural risk assessment (stub FEA)."""
    risk_level: str = "low"        # "low" | "medium" | "high"
    risk_score: float = 0.0        # 0-100
    thin_section_risk: str = "low"
    aspect_ratio_risk: str = "low"
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "risk_level": self.risk_level,
            "risk_score": round(self.risk_score, 2),
            "thin_section_risk": self.thin_section_risk,
            "aspect_ratio_risk": self.aspect_ratio_risk,
            "notes": self.notes,
        }


def compare_meshes(path_a: Path, path_b: Path) -> GeometricDiff:
    """Compare two STL files using existing analyze_mesh().

    Computes deltas in volume, surface area, bounding box, and center of mass.
    """
    a = analyze_mesh(path_a)
    b = analyze_mesh(path_b)

    vol_a = a.volume_mm3
    vol_b = b.volume_mm3
    vol_delta = vol_b - vol_a
    vol_pct = (vol_delta / vol_a * 100.0) if vol_a != 0 else 0.0

    bbox_delta = {}
    for key in ("size_x", "size_y", "size_z"):
        bbox_delta[key] = b.bounding_box.get(key, 0.0) - a.bounding_box.get(key, 0.0)

    com_delta = []
    for i in range(min(len(a.center_of_mass), len(b.center_of_mass))):
        com_delta.append(b.center_of_mass[i] - a.center_of_mass[i])

    return GeometricDiff(
        volume_delta_mm3=vol_delta,
        volume_delta_pct=vol_pct,
        surface_area_delta_mm2=b.surface_area_mm2 - a.surface_area_mm2,
        bbox_size_delta=bbox_delta,
        center_of_mass_delta=com_delta,
    )


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
        z_component = mesh.face_normals[:, 2]
        overhang_threshold = -np.cos(np.radians(max_overhang_angle))
        overhang_faces = np.sum(z_component < overhang_threshold)
        overhang_ratio = overhang_faces / len(mesh.faces)
        if overhang_ratio > 0.05:
            report.overhang_ok = False
            report.issues.append(
                f"{overhang_ratio:.0%} of faces exceed {max_overhang_angle}\u00b0 overhang limit"
            )
            report.suggestions.append("Add supports or reorient the model")

    # Wall thickness check (watertight meshes only)
    if mesh.is_watertight and min_wall_thickness > 0:
        thin_count, total_sampled, _ = _check_wall_thickness(mesh, min_wall_thickness)
        report.thin_wall_count = thin_count
        report.thin_wall_samples = total_sampled
        if thin_count > 0:
            report.min_wall_ok = False
            ratio_pct = thin_count / max(total_sampled, 1) * 100
            report.issues.append(
                f"{thin_count}/{total_sampled} sampled points ({ratio_pct:.0f}%) "
                f"have wall thickness < {min_wall_thickness}mm"
            )
            report.suggestions.append(
                f"Increase wall thickness to at least {min_wall_thickness}mm"
            )

    # Watertightness
    if not mesh.is_watertight:
        report.issues.append("Mesh is not watertight \u2014 may cause slicing issues")
        report.suggestions.append("Repair mesh in MeshLab or Meshmixer")

    return report


# ---------------------------------------------------------------------------
# Wall thickness helper
# ---------------------------------------------------------------------------

def _check_wall_thickness(
    mesh: Any,
    min_wall_thickness: float,
    max_samples: int = 500,
) -> tuple[int, int, list[list[float]]]:
    """Check wall thickness via inward ray casting on face centroids.

    Args:
        mesh: A trimesh.Trimesh object (must be watertight).
        min_wall_thickness: Minimum acceptable wall thickness in mm.
        max_samples: Maximum face centroids to sample.

    Returns:
        (thin_count, total_sampled, thin_locations) where thin_locations
        is a list of [x, y, z] points that are too thin.
    """
    import numpy as np

    if not mesh.is_watertight:
        return (0, 0, [])

    n_faces = len(mesh.faces)
    if n_faces == 0:
        return (0, 0, [])

    # Select evenly spaced face indices
    if n_faces <= max_samples:
        indices = np.arange(n_faces)
    else:
        indices = np.linspace(0, n_faces - 1, max_samples, dtype=int)

    centroids = mesh.triangles_center[indices]
    normals = mesh.face_normals[indices]

    # Offset origins slightly inward to avoid self-intersection
    origins = centroids - normals * 1e-4
    directions = -normals

    locations, index_ray, _ = mesh.ray.intersects_location(
        ray_origins=origins,
        ray_directions=directions,
    )

    thin_count = 0
    thin_locations: list[list[float]] = []

    # For each ray, find the nearest hit distance
    for i in range(len(indices)):
        hits = locations[index_ray == i]
        if len(hits) == 0:
            continue
        distances = np.linalg.norm(hits - origins[i], axis=1)
        min_dist = float(np.min(distances))
        if min_dist < min_wall_thickness:
            thin_count += 1
            thin_locations.append(centroids[i].tolist())

    return (thin_count, len(indices), thin_locations)


# ---------------------------------------------------------------------------
# Algorithmic fidelity scoring
# ---------------------------------------------------------------------------

def compute_algorithmic_fidelity(
    sandbox_eval: dict[str, Any],
    critical_dimensions: dict[str, Any],
    dfm_report: dict[str, Any] | None = None,
) -> AlgorithmicFidelityResult:
    """Compute an algorithmic fidelity score from sandbox evaluation data.

    Operates on plain dicts to stay decoupled from Pydantic models.

    Args:
        sandbox_eval: Dict with keys like bounding_box, is_watertight, volume_mm3.
        critical_dimensions: Dict mapping dimension names to expected values (mm).
        dfm_report: Optional structured DFM report dict.

    Returns:
        AlgorithmicFidelityResult with sub-scores and overall weighted score.
    """
    result = AlgorithmicFidelityResult()
    bbox = sandbox_eval.get("bounding_box", {})

    # --- Dimension match ---
    _SUFFIX_MAP = {
        "_length": "size_x", "_x": "size_x",
        "_width": "size_y", "_y": "size_y",
        "_height": "size_z", "_z": "size_z",
    }

    dim_scores: list[float] = []
    for name, expected_raw in critical_dimensions.items():
        try:
            expected = float(str(expected_raw).replace("mm", "").strip())
        except (ValueError, TypeError):
            continue
        if expected <= 0:
            continue

        # Determine which bbox axis to compare
        actual: float | None = None
        name_lower = name.lower()

        if name_lower.endswith("_diameter"):
            sx = bbox.get("size_x", 0)
            sy = bbox.get("size_y", 0)
            actual = max(sx, sy)
        else:
            for suffix, bbox_key in _SUFFIX_MAP.items():
                if name_lower.endswith(suffix):
                    actual = bbox.get(bbox_key)
                    break

        if actual is not None:
            score = max(0.0, 1.0 - abs(actual - expected) / expected) * 100
            dim_scores.append(score)
            result.dimension_details[name] = score

    if dim_scores:
        result.dimension_match_score = sum(dim_scores) / len(dim_scores)
    else:
        result.dimension_match_score = 50.0  # default when no dimensions mapped
        result.notes.append("No critical dimensions could be mapped to bounding box")

    # --- Volume sanity ---
    result.volume_sanity_score = 100.0  # default
    if bbox:
        sx = bbox.get("size_x", 0)
        sy = bbox.get("size_y", 0)
        sz = bbox.get("size_z", 0)
        bbox_volume = sx * sy * sz
        actual_volume = sandbox_eval.get("volume_mm3", 0)

        if bbox_volume > 0 and actual_volume > 0:
            ratio = actual_volume / bbox_volume
            if 0.10 <= ratio <= 1.0:
                result.volume_sanity_score = 100.0
            elif ratio < 0.10:
                result.volume_sanity_score = max(0.0, ratio / 0.10 * 100)
                result.notes.append(
                    f"Volume ratio {ratio:.2f} is very low (< 10% of bounding box)"
                )
            else:
                # ratio > 1.0 shouldn't happen for watertight, but handle gracefully
                result.volume_sanity_score = max(0.0, 100 - (ratio - 1.0) * 100)
                result.notes.append(f"Volume ratio {ratio:.2f} exceeds bounding box")
        elif actual_volume <= 0 and sandbox_eval.get("is_watertight"):
            result.volume_sanity_score = 0.0
            result.notes.append("Watertight mesh but zero/negative volume")

    # --- DFM score ---
    dfm_s = 100.0
    is_watertight = sandbox_eval.get("is_watertight", False)
    if not is_watertight:
        dfm_s -= 40
        result.notes.append("DFM: not watertight (-40)")

    if dfm_report:
        if not dfm_report.get("build_volume_ok", True):
            dfm_s -= 30
            result.notes.append("DFM: build volume violation (-30)")
        for issue in dfm_report.get("issues", []):
            if "watertight" not in issue.lower() and "build volume" not in issue.lower():
                dfm_s -= 10
        if dfm_report.get("fea_risk_level") == "high" or sandbox_eval.get("fea_risk_level") == "high":
            dfm_s -= 15
            result.notes.append("DFM: FEA high risk (-15)")

    result.dfm_score = max(0.0, min(100.0, dfm_s))

    # --- Overall weighted ---
    result.overall_score = (
        result.dimension_match_score * 0.40
        + result.volume_sanity_score * 0.20
        + result.dfm_score * 0.40
    )

    return result


# ---------------------------------------------------------------------------
# FEA stub
# ---------------------------------------------------------------------------

def run_fea_stub(
    path: Path,
    min_wall_thickness: float = 0.8,
) -> FEAStubResult:
    """Run a lightweight structural risk assessment on a mesh.

    Checks thin sections, aspect ratio, and volume/surface-area ratio
    to estimate structural risk without full FEA.

    Args:
        path: Path to mesh file.
        min_wall_thickness: Minimum wall thickness in mm.

    Returns:
        FEAStubResult with risk level and contributing factors.
    """
    import numpy as np
    import trimesh

    result = FEAStubResult()
    score = 0.0

    mesh = trimesh.load(str(path))
    if isinstance(mesh, trimesh.Scene):
        meshes = list(mesh.geometry.values())
        if not meshes:
            result.notes.append("Empty mesh — cannot assess risk")
            return result
        mesh = trimesh.util.concatenate(meshes)

    # --- Thin sections ---
    if mesh.is_watertight:
        thin_count, total_sampled, _ = _check_wall_thickness(
            mesh, min_wall_thickness,
        )
        if total_sampled > 0:
            thin_ratio = thin_count / total_sampled
            if thin_ratio > 0.20:
                result.thin_section_risk = "high"
                score += 35
                result.notes.append(
                    f"Thin sections: {thin_ratio:.0%} of samples below {min_wall_thickness}mm"
                )
            elif thin_ratio > 0.05:
                result.thin_section_risk = "medium"
                score += 15
                result.notes.append(
                    f"Some thin sections: {thin_ratio:.0%} of samples below {min_wall_thickness}mm"
                )

    # --- Aspect ratio ---
    bounds = mesh.bounds
    sizes = bounds[1] - bounds[0]
    sizes_sorted = np.sort(sizes)
    shortest = sizes_sorted[0] if sizes_sorted[0] > 1e-6 else 1e-6
    longest = sizes_sorted[2]
    aspect = longest / shortest

    if aspect > 20:
        result.aspect_ratio_risk = "high"
        score += 30
        result.notes.append(f"Extreme aspect ratio: {aspect:.1f}:1")
    elif aspect > 8:
        result.aspect_ratio_risk = "medium"
        score += 15
        result.notes.append(f"High aspect ratio: {aspect:.1f}:1")

    # --- Volume / surface-area ratio (shell-like geometry detection) ---
    if mesh.is_watertight and mesh.volume > 0 and mesh.area > 0:
        diagonal = float(np.linalg.norm(sizes))
        if diagonal > 0:
            # Normalize: a solid cube has V/(SA*diag) ~ 0.068
            normalized = mesh.volume / (mesh.area * diagonal)
            if normalized < 0.01:
                score += 20
                result.notes.append(
                    f"Shell-like geometry (V/SA*diag = {normalized:.4f})"
                )
            elif normalized < 0.03:
                score += 10
                result.notes.append(
                    f"Relatively thin geometry (V/SA*diag = {normalized:.4f})"
                )

    # --- Classify ---
    result.risk_score = min(100.0, score)
    if score >= 50:
        result.risk_level = "high"
    elif score >= 25:
        result.risk_level = "medium"
    else:
        result.risk_level = "low"

    return result
