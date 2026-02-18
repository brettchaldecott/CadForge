"""Tests for CadQuery execution route.

These tests work without CadQuery installed by testing error handling.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from cadforge_engine.app import create_app


@pytest.fixture
def client() -> TestClient:
    app = create_app()
    return TestClient(app)


def test_cadquery_missing_dependency(client: TestClient, tmp_path: Path) -> None:
    """Test that CadQuery route handles missing cadquery gracefully."""
    response = client.post("/tools/cadquery", json={
        "code": "result = cq.Workplane('XY').box(10, 10, 10)",
        "output_name": "test_box",
        "format": "stl",
        "project_root": str(tmp_path),
    })
    assert response.status_code == 200
    data = response.json()
    # If cadquery is installed, success=True; if not, the sandbox
    # will fail gracefully since 'cq' won't be in namespace
    assert "success" in data


def test_cadquery_syntax_error(client: TestClient, tmp_path: Path) -> None:
    """Test that syntax errors are reported cleanly."""
    response = client.post("/tools/cadquery", json={
        "code": "def broken(",
        "output_name": "broken",
        "format": "stl",
        "project_root": str(tmp_path),
    })
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is False
    assert data["error"] is not None


def test_cadquery_pure_python(client: TestClient, tmp_path: Path) -> None:
    """Test executing pure Python code without CadQuery."""
    response = client.post("/tools/cadquery", json={
        "code": "x = 2 + 2\nprint(f'result is {x}')",
        "output_name": "pure",
        "format": "stl",
        "project_root": str(tmp_path),
    })
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert "result is 4" in data["stdout"]
    assert data["message"] == "Code executed successfully (no result variable set)"
