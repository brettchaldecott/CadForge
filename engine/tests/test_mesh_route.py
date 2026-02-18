"""Tests for mesh analysis route."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from cadforge_engine.app import create_app


@pytest.fixture
def client() -> TestClient:
    app = create_app()
    return TestClient(app)


def test_mesh_file_not_found(client: TestClient, tmp_path: Path) -> None:
    response = client.post("/tools/mesh", json={
        "path": str(tmp_path / "nonexistent.stl"),
        "project_root": str(tmp_path),
    })
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is False
    assert "not found" in data["error"].lower()


def test_preview_file_not_found(client: TestClient, tmp_path: Path) -> None:
    response = client.post("/tools/preview", json={
        "path": str(tmp_path / "nonexistent.stl"),
    })
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is False
    assert "not found" in data["error"].lower()
