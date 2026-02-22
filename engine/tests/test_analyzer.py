"""Tests for mesh analysis and geometric comparison."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from cadforge_engine.domain.analyzer import (
    GeometricDiff,
    MeshAnalysis,
    compare_meshes,
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
