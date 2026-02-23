"""Tests for build123d support in the sandbox.

Tests verify that build123d code can be executed and exported via the sandbox.
Tests are skipped if build123d is not installed.
"""

from __future__ import annotations

from pathlib import Path

import pytest

# Skip entire module if build123d is not available
build123d = pytest.importorskip("build123d")

from cadforge_engine.domain.sandbox import build_namespace, execute_cadquery


class TestBuild123dNamespace:
    """Test that build123d is available in the sandbox namespace."""

    def test_bd_in_namespace(self) -> None:
        ns = build_namespace()
        assert "bd" in ns
        assert "build123d" in ns

    def test_top_level_names(self) -> None:
        ns = build_namespace()
        for name in ("Box", "Cylinder", "Sphere", "BuildPart", "BuildSketch",
                      "extrude", "Mode", "Align", "export_stl", "export_step"):
            assert name in ns, f"{name} not found in sandbox namespace"

    def test_cq_also_present(self) -> None:
        """CadQuery should still be in namespace if installed."""
        ns = build_namespace()
        # We don't assert cq is present because it may not be installed,
        # but we verify bd didn't break anything
        assert "math" in ns
        assert "bd" in ns


class TestBuild123dExecution:
    """Test executing build123d code in the sandbox."""

    def test_simple_box(self) -> None:
        code = """\
with BuildPart() as part:
    Box(10, 20, 5)
result = part.part
"""
        result = execute_cadquery(code)
        assert result.success, f"Execution failed: {result.error}"
        assert result.result is not None

    def test_cylinder_with_hole(self) -> None:
        code = """\
with BuildPart() as part:
    Cylinder(radius=10, height=20)
    Cylinder(radius=5, height=20, mode=Mode.SUBTRACT)
result = part.part
"""
        result = execute_cadquery(code)
        assert result.success, f"Execution failed: {result.error}"
        assert result.result is not None

    def test_using_bd_namespace(self) -> None:
        code = """\
with bd.BuildPart() as part:
    bd.Box(15, 15, 10)
result = part.part
"""
        result = execute_cadquery(code)
        assert result.success, f"Execution failed: {result.error}"
        assert result.result is not None

    def test_sketch_and_extrude(self) -> None:
        code = """\
with BuildPart() as part:
    with BuildSketch() as sk:
        Rectangle(20, 10)
    extrude(amount=5)
result = part.part
"""
        result = execute_cadquery(code)
        assert result.success, f"Execution failed: {result.error}"
        assert result.result is not None


class TestBuild123dExport:
    """Test exporting build123d results."""

    def test_export_stl(self, tmp_path: Path) -> None:
        code = """\
with BuildPart() as part:
    Box(10, 10, 10)
result = part.part
"""
        output = tmp_path / "test_box.stl"
        result = execute_cadquery(code, output_path=output)
        assert result.success, f"Execution failed: {result.error}"
        assert output.exists(), "STL file was not created"
        assert output.stat().st_size > 0, "STL file is empty"

    def test_export_step(self, tmp_path: Path) -> None:
        code = """\
with BuildPart() as part:
    Box(10, 10, 10)
result = part.part
"""
        output = tmp_path / "test_box.step"
        result = execute_cadquery(code, output_path=output)
        assert result.success, f"Execution failed: {result.error}"
        assert output.exists(), "STEP file was not created"
        assert output.stat().st_size > 0, "STEP file is empty"

    def test_user_vars_exclude_build123d_names(self) -> None:
        code = """\
my_var = 42
with BuildPart() as part:
    Box(10, 10, 10)
result = part.part
"""
        result = execute_cadquery(code)
        assert result.success
        # User variable should be present
        assert "my_var" in result.variables
        # build123d namespace names should NOT be in user vars
        for name in ("Box", "Cylinder", "BuildPart", "bd", "build123d"):
            assert name not in result.variables, f"{name} leaked into user_vars"
