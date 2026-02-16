"""Tests for mesh analysis.

Uses mock trimesh objects since actual mesh files may not be available.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from cadforge.cad.analyzer import (
    DFMReport,
    MeshAnalysis,
    check_build_volume,
)


class TestMeshAnalysis:
    def test_defaults(self):
        a = MeshAnalysis(file_path="test.stl")
        assert a.is_watertight is False
        assert a.volume_mm3 == 0.0
        assert a.issues == []

    def test_volume_conversion(self):
        a = MeshAnalysis(file_path="test.stl", volume_mm3=5000.0)
        assert a.volume_cm3 == 5.0

    def test_to_dict(self):
        a = MeshAnalysis(
            file_path="test.stl",
            is_watertight=True,
            volume_mm3=1234.56,
            triangle_count=100,
        )
        d = a.to_dict()
        assert d["file_path"] == "test.stl"
        assert d["is_watertight"] is True
        assert d["volume_mm3"] == 1234.56
        assert d["volume_cm3"] == 1.23
        assert d["triangle_count"] == 100

    def test_to_dict_includes_issues(self):
        a = MeshAnalysis(file_path="test.stl", issues=["not watertight"])
        d = a.to_dict()
        assert "not watertight" in d["issues"]


class TestCheckBuildVolume:
    def test_fits(self):
        a = MeshAnalysis(
            file_path="test.stl",
            bounding_box={"size_x": 50, "size_y": 50, "size_z": 50},
        )
        issues = check_build_volume(a, 250, 210, 220)
        assert issues == []

    def test_exceeds_x(self):
        a = MeshAnalysis(
            file_path="test.stl",
            bounding_box={"size_x": 300, "size_y": 50, "size_z": 50},
        )
        issues = check_build_volume(a, 250, 210, 220)
        assert len(issues) == 1
        assert "X" in issues[0]

    def test_exceeds_all(self):
        a = MeshAnalysis(
            file_path="test.stl",
            bounding_box={"size_x": 300, "size_y": 300, "size_z": 300},
        )
        issues = check_build_volume(a, 250, 210, 220)
        assert len(issues) == 3

    def test_empty_bounding_box(self):
        a = MeshAnalysis(file_path="test.stl")
        issues = check_build_volume(a, 250, 210, 220)
        assert issues == []


class TestDFMReport:
    def test_passed_when_no_issues(self):
        r = DFMReport()
        assert r.passed is True

    def test_failed_with_issues(self):
        r = DFMReport(issues=["Wall too thin"])
        assert r.passed is False

    def test_to_dict(self):
        r = DFMReport(
            printer_name="Prusa MK4",
            issues=["Overhang too steep"],
            suggestions=["Add supports"],
        )
        d = r.to_dict()
        assert d["printer"] == "Prusa MK4"
        assert d["passed"] is False
        assert len(d["issues"]) == 1
        assert len(d["suggestions"]) == 1
