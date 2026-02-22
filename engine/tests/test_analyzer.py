"""Tests for mesh analysis and geometric comparison."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from cadforge_engine.domain.analyzer import (
    AlgorithmicFidelityResult,
    DFMReport,
    FEAStubResult,
    GeometricDiff,
    MeshAnalysis,
    _check_wall_thickness,
    compute_algorithmic_fidelity,
    compare_meshes,
    run_fea_stub,
)


def _make_analysis(
    volume: float = 1000.0,
    surface_area: float = 600.0,
    bbox: dict | None = None,
    com: list | None = None,
    watertight: bool = True,
) -> MeshAnalysis:
    """Create a MeshAnalysis for testing."""
    return MeshAnalysis(
        file_path="test.stl",
        is_watertight=watertight,
        volume_mm3=volume,
        surface_area_mm2=surface_area,
        bounding_box=bbox or {"size_x": 10.0, "size_y": 10.0, "size_z": 10.0},
        center_of_mass=com or [5.0, 5.0, 5.0],
    )


class TestGeometricDiff:
    def test_to_dict(self):
        diff = GeometricDiff(
            volume_delta_mm3=100.5,
            volume_delta_pct=10.05,
            surface_area_delta_mm2=50.3,
            bbox_size_delta={"size_x": 1.1, "size_y": 2.2, "size_z": 0.0},
            center_of_mass_delta=[0.5, -0.3, 0.0],
        )
        d = diff.to_dict()
        assert d["volume_delta_mm3"] == 100.5
        assert d["volume_delta_pct"] == 10.05
        assert d["bbox_size_delta"]["size_x"] == 1.1

    def test_defaults(self):
        diff = GeometricDiff()
        assert diff.volume_delta_mm3 == 0.0
        assert diff.bbox_size_delta == {}
        assert diff.center_of_mass_delta == []


class TestCompareMeshes:
    @patch("cadforge_engine.domain.analyzer.analyze_mesh")
    def test_compare_meshes(self, mock_analyze):
        """Compare two different meshes."""
        mock_analyze.side_effect = [
            _make_analysis(volume=1000.0, surface_area=600.0,
                          bbox={"size_x": 10.0, "size_y": 10.0, "size_z": 10.0},
                          com=[5.0, 5.0, 5.0]),
            _make_analysis(volume=1200.0, surface_area=650.0,
                          bbox={"size_x": 12.0, "size_y": 10.0, "size_z": 10.0},
                          com=[6.0, 5.0, 5.0]),
        ]

        diff = compare_meshes(Path("a.stl"), Path("b.stl"))
        assert diff.volume_delta_mm3 == 200.0
        assert diff.volume_delta_pct == pytest.approx(20.0)
        assert diff.surface_area_delta_mm2 == 50.0
        assert diff.bbox_size_delta["size_x"] == 2.0
        assert diff.bbox_size_delta["size_y"] == 0.0
        assert diff.center_of_mass_delta[0] == 1.0

    @patch("cadforge_engine.domain.analyzer.analyze_mesh")
    def test_compare_identical_meshes(self, mock_analyze):
        """Identical meshes should produce zero diff."""
        analysis = _make_analysis()
        mock_analyze.side_effect = [analysis, analysis]

        diff = compare_meshes(Path("a.stl"), Path("a.stl"))
        assert diff.volume_delta_mm3 == 0.0
        assert diff.volume_delta_pct == 0.0
        assert diff.surface_area_delta_mm2 == 0.0
        for v in diff.bbox_size_delta.values():
            assert v == 0.0
        for v in diff.center_of_mass_delta:
            assert v == 0.0

    @patch("cadforge_engine.domain.analyzer.analyze_mesh")
    def test_compare_zero_volume(self, mock_analyze):
        """Handle zero-volume mesh (avoid division by zero)."""
        mock_analyze.side_effect = [
            _make_analysis(volume=0.0, watertight=False),
            _make_analysis(volume=100.0),
        ]

        diff = compare_meshes(Path("a.stl"), Path("b.stl"))
        assert diff.volume_delta_mm3 == 100.0
        assert diff.volume_delta_pct == 0.0  # Avoid division by zero


# ---------------------------------------------------------------------------
# Algorithmic fidelity scoring
# ---------------------------------------------------------------------------


class TestAlgorithmicFidelity:
    def test_dimension_match_perfect(self):
        """Exact match on all dimensions should give 100."""
        sandbox_eval = {
            "bounding_box": {"size_x": 50.0, "size_y": 30.0, "size_z": 20.0},
            "is_watertight": True,
            "volume_mm3": 15000.0,
        }
        dims = {"part_length": "50mm", "part_width": "30mm", "part_height": "20mm"}
        result = compute_algorithmic_fidelity(sandbox_eval, dims)
        assert result.dimension_match_score == pytest.approx(100.0)

    def test_dimension_match_partial(self):
        """20% off on one axis should produce a partial score."""
        sandbox_eval = {
            "bounding_box": {"size_x": 60.0, "size_y": 30.0, "size_z": 20.0},
            "is_watertight": True,
            "volume_mm3": 18000.0,
        }
        # Expected X = 50, actual = 60 → 20% off → per-dim score = 80
        dims = {"part_length": "50mm", "part_width": "30mm", "part_height": "20mm"}
        result = compute_algorithmic_fidelity(sandbox_eval, dims)
        # (80 + 100 + 100) / 3 ≈ 93.33
        assert 90 < result.dimension_match_score < 95

    def test_dimension_match_no_dimensions(self):
        """Empty dimensions should give default 50."""
        sandbox_eval = {
            "bounding_box": {"size_x": 50.0, "size_y": 30.0, "size_z": 20.0},
            "is_watertight": True,
            "volume_mm3": 15000.0,
        }
        result = compute_algorithmic_fidelity(sandbox_eval, {})
        assert result.dimension_match_score == 50.0

    def test_dimension_suffix_mapping(self):
        """Test all suffix→bbox key mappings."""
        sandbox_eval = {
            "bounding_box": {"size_x": 100.0, "size_y": 80.0, "size_z": 60.0},
            "is_watertight": True,
            "volume_mm3": 240000.0,
        }
        # _x → size_x, _y → size_y, _z → size_z
        dims = {"dim_x": "100", "dim_y": "80", "dim_z": "60"}
        result = compute_algorithmic_fidelity(sandbox_eval, dims)
        assert result.dimension_match_score == pytest.approx(100.0)

    def test_dimension_diameter_mapping(self):
        """_diameter should map to max(size_x, size_y)."""
        sandbox_eval = {
            "bounding_box": {"size_x": 40.0, "size_y": 50.0, "size_z": 20.0},
            "is_watertight": True,
            "volume_mm3": 20000.0,
        }
        dims = {"outer_diameter": "50"}
        result = compute_algorithmic_fidelity(sandbox_eval, dims)
        assert result.dimension_match_score == pytest.approx(100.0)

    def test_volume_sanity_in_range(self):
        """Volume between 10-100% of bbox volume should score 100."""
        bbox_vol = 50 * 30 * 20  # 30000
        sandbox_eval = {
            "bounding_box": {"size_x": 50.0, "size_y": 30.0, "size_z": 20.0},
            "is_watertight": True,
            "volume_mm3": bbox_vol * 0.5,  # 50% fill = in range
        }
        result = compute_algorithmic_fidelity(sandbox_eval, {})
        assert result.volume_sanity_score == 100.0

    def test_volume_sanity_out_of_range(self):
        """Volume < 10% of bbox volume should penalize."""
        bbox_vol = 50 * 30 * 20  # 30000
        sandbox_eval = {
            "bounding_box": {"size_x": 50.0, "size_y": 30.0, "size_z": 20.0},
            "is_watertight": True,
            "volume_mm3": bbox_vol * 0.01,  # 1% fill = very low
        }
        result = compute_algorithmic_fidelity(sandbox_eval, {})
        assert result.volume_sanity_score < 20

    def test_dfm_score_clean(self):
        """Watertight mesh with no DFM issues should score 100."""
        sandbox_eval = {
            "bounding_box": {"size_x": 50.0, "size_y": 30.0, "size_z": 20.0},
            "is_watertight": True,
            "volume_mm3": 15000.0,
        }
        result = compute_algorithmic_fidelity(sandbox_eval, {}, dfm_report={"passed": True, "issues": []})
        assert result.dfm_score == 100.0

    def test_dfm_score_penalties(self):
        """Not watertight should reduce DFM score by 40."""
        sandbox_eval = {
            "bounding_box": {"size_x": 50.0, "size_y": 30.0, "size_z": 20.0},
            "is_watertight": False,
            "volume_mm3": 0.0,
        }
        result = compute_algorithmic_fidelity(sandbox_eval, {})
        assert result.dfm_score == pytest.approx(60.0)

    def test_overall_weighted(self):
        """Overall should be weighted 40% dim + 20% volume + 40% DFM."""
        sandbox_eval = {
            "bounding_box": {"size_x": 50.0, "size_y": 30.0, "size_z": 20.0},
            "is_watertight": True,
            "volume_mm3": 15000.0,
        }
        dims = {"part_length": "50mm", "part_width": "30mm", "part_height": "20mm"}
        result = compute_algorithmic_fidelity(sandbox_eval, dims)
        expected = (
            result.dimension_match_score * 0.40
            + result.volume_sanity_score * 0.20
            + result.dfm_score * 0.40
        )
        assert result.overall_score == pytest.approx(expected)


# ---------------------------------------------------------------------------
# Wall thickness
# ---------------------------------------------------------------------------


def _make_mock_mesh(is_watertight=True, n_faces=100, face_normals=None,
                    triangles_center=None, ray_hits=None, ray_indices=None):
    """Build a mock trimesh object for wall thickness testing."""
    mesh = MagicMock()
    mesh.is_watertight = is_watertight
    mesh.faces = np.zeros((n_faces, 3), dtype=int)

    if face_normals is None:
        face_normals = np.tile([0, 0, 1.0], (n_faces, 1))
    mesh.face_normals = face_normals

    if triangles_center is None:
        triangles_center = np.random.rand(n_faces, 3) * 50
    mesh.triangles_center = triangles_center

    mock_ray = MagicMock()
    if ray_hits is not None and ray_indices is not None:
        mock_ray.intersects_location.return_value = (ray_hits, ray_indices, None)
    else:
        mock_ray.intersects_location.return_value = (np.zeros((0, 3)), np.array([], dtype=int), None)
    mesh.ray = mock_ray

    return mesh


class TestWallThickness:
    def test_thick_walls(self):
        """All rays hit far away → min_wall_ok stays True."""
        n = 10
        centers = np.tile([25.0, 25.0, 50.0], (n, 1))
        normals = np.tile([0, 0, 1.0], (n, 1))
        # Hits are 5mm away (far from each origin)
        hit_locs = centers - normals * 5.0
        ray_indices = np.arange(n)
        mesh = _make_mock_mesh(
            n_faces=n, face_normals=normals, triangles_center=centers,
            ray_hits=hit_locs, ray_indices=ray_indices,
        )
        thin_count, total, _ = _check_wall_thickness(mesh, min_wall_thickness=0.8)
        assert thin_count == 0
        assert total == n

    def test_thin_walls(self):
        """All rays hit very close → thin detected."""
        n = 10
        centers = np.tile([25.0, 25.0, 50.0], (n, 1))
        normals = np.tile([0, 0, 1.0], (n, 1))
        # Origins offset by 1e-4, hits only 0.3mm from origin
        origins = centers - normals * 1e-4
        hit_locs = origins - normals * 0.3
        ray_indices = np.arange(n)
        mesh = _make_mock_mesh(
            n_faces=n, face_normals=normals, triangles_center=centers,
            ray_hits=hit_locs, ray_indices=ray_indices,
        )
        thin_count, total, thin_locs = _check_wall_thickness(mesh, min_wall_thickness=0.8)
        assert thin_count == n
        assert total == n
        assert len(thin_locs) == n

    def test_not_watertight_skips(self):
        """Non-watertight mesh should skip wall check entirely."""
        mesh = _make_mock_mesh(is_watertight=False)
        thin_count, total, _ = _check_wall_thickness(mesh, min_wall_thickness=0.8)
        assert thin_count == 0
        assert total == 0


# ---------------------------------------------------------------------------
# FEA stub
# ---------------------------------------------------------------------------


class TestFEAStub:
    @patch("trimesh.load")
    def test_low_risk_cube(self, mock_load):
        """A solid cube should be low risk."""
        mesh = MagicMock()
        mesh.is_watertight = True
        mesh.bounds = np.array([[0, 0, 0], [50, 50, 50]], dtype=float)
        mesh.volume = 125000.0  # 50^3
        mesh.area = 15000.0  # 6 * 50^2
        mesh.faces = np.zeros((100, 3))
        mesh.face_normals = np.tile([0, 0, 1.0], (100, 1))
        mesh.triangles_center = np.random.rand(100, 3) * 50
        # Ray hits far away (thick walls)
        origins = mesh.triangles_center - mesh.face_normals * 1e-4
        hit_locs = origins - mesh.face_normals * 20.0
        mock_ray = MagicMock()
        mock_ray.intersects_location.return_value = (
            hit_locs, np.arange(100), None,
        )
        mesh.ray = mock_ray
        mock_load.return_value = mesh

        result = run_fea_stub(Path("cube.stl"))
        assert result.risk_level == "low"
        assert result.risk_score < 25

    @patch("trimesh.load")
    def test_high_aspect_ratio(self, mock_load):
        """Extreme aspect ratio should trigger medium/high risk."""
        mesh = MagicMock()
        mesh.is_watertight = True
        mesh.bounds = np.array([[0, 0, 0], [200, 5, 5]], dtype=float)
        mesh.volume = 5000.0
        mesh.area = 4100.0
        mesh.faces = np.zeros((10, 3))
        mesh.face_normals = np.tile([0, 0, 1.0], (10, 1))
        mesh.triangles_center = np.random.rand(10, 3)
        mock_ray = MagicMock()
        mock_ray.intersects_location.return_value = (
            np.zeros((0, 3)), np.array([], dtype=int), None,
        )
        mesh.ray = mock_ray
        mock_load.return_value = mesh

        result = run_fea_stub(Path("thin_rod.stl"))
        # 200/5 = 40:1 → high aspect ratio risk
        assert result.aspect_ratio_risk == "high"
        assert result.risk_score >= 25

    @patch("trimesh.load")
    def test_thin_sections(self, mock_load):
        """Many thin wall hits should flag high thin-section risk."""
        n = 50
        mesh = MagicMock()
        mesh.is_watertight = True
        mesh.bounds = np.array([[0, 0, 0], [50, 50, 50]], dtype=float)
        mesh.volume = 125000.0
        mesh.area = 15000.0
        mesh.faces = np.zeros((n, 3))
        normals = np.tile([0, 0, 1.0], (n, 1))
        mesh.face_normals = normals
        centers = np.random.rand(n, 3) * 50
        mesh.triangles_center = centers
        # All hits very close = thin walls
        origins = centers - normals * 1e-4
        hit_locs = origins - normals * 0.2  # 0.2mm thick
        mock_ray = MagicMock()
        mock_ray.intersects_location.return_value = (
            hit_locs, np.arange(n), None,
        )
        mesh.ray = mock_ray
        mock_load.return_value = mesh

        result = run_fea_stub(Path("thin_shell.stl"))
        assert result.thin_section_risk == "high"
        assert result.risk_score >= 35
