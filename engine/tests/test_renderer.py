"""Tests for headless STL to PNG rendering.

Tests are skipped if pyvista is not available.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pyvista = pytest.importorskip("pyvista")


def _create_test_stl(tmp_path: Path) -> Path:
    """Create a simple STL file using pyvista for testing."""
    import pyvista as pv

    box = pv.Box()
    stl_path = tmp_path / "test_box.stl"
    box.save(str(stl_path))
    return stl_path


class TestRenderer:
    """Test headless renderer."""

    def test_render_produces_pngs(self, tmp_path: Path) -> None:
        from cadforge_engine.domain.renderer import render_stl_to_png

        stl_path = _create_test_stl(tmp_path)
        png_base = tmp_path / "output" / "test_box"

        paths = render_stl_to_png(stl_path, png_base)

        assert len(paths) == 3
        for p in paths:
            assert p.exists(), f"PNG not created: {p}"
            assert p.stat().st_size > 0, f"PNG is empty: {p}"

    def test_render_view_names(self, tmp_path: Path) -> None:
        from cadforge_engine.domain.renderer import render_stl_to_png

        stl_path = _create_test_stl(tmp_path)
        png_base = tmp_path / "test_box"

        paths = render_stl_to_png(stl_path, png_base)

        names = [p.stem for p in paths]
        assert "test_box_isometric" in names
        assert "test_box_front" in names
        assert "test_box_right" in names

    def test_custom_camera_angles(self, tmp_path: Path) -> None:
        from cadforge_engine.domain.renderer import render_stl_to_png

        stl_path = _create_test_stl(tmp_path)
        png_base = tmp_path / "test_box"

        paths = render_stl_to_png(
            stl_path,
            png_base,
            camera_angles=[(0, 90, 0)],
        )

        assert len(paths) == 1
        assert paths[0].exists()
