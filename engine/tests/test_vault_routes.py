"""Tests for vault API routes."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from cadforge_engine.app import create_app


@pytest.fixture
def client() -> TestClient:
    app = create_app()
    return TestClient(app)


@pytest.fixture
def tmp_project(tmp_path: Path) -> Path:
    """Create a temporary project with a vault directory."""
    vault_dir = tmp_path / "vault"
    vault_dir.mkdir()
    (vault_dir / "test.md").write_text(
        "---\ntags: [design, cad]\n---\n\n# Test Document\n\nThis is test content about gears.\n\n## Details\n\nGear teeth are important for mechanical design.\n",
        encoding="utf-8",
    )
    return tmp_path


def test_vault_search_no_vault(client: TestClient, tmp_path: Path) -> None:
    response = client.post("/vault/search", json={
        "query": "test",
        "project_root": str(tmp_path),
    })
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["results"] == [] or data["note"] is not None


def test_vault_search_fallback(client: TestClient, tmp_project: Path) -> None:
    response = client.post("/vault/search", json={
        "query": "gears",
        "project_root": str(tmp_project),
    })
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True


def test_vault_index(client: TestClient, tmp_project: Path) -> None:
    response = client.post("/vault/index", json={
        "project_root": str(tmp_project),
        "incremental": False,
    })
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["files_indexed"] >= 1
    assert data["chunks_created"] >= 1


def test_vault_index_then_search(client: TestClient, tmp_project: Path) -> None:
    # Index first
    client.post("/vault/index", json={
        "project_root": str(tmp_project),
        "incremental": False,
    })

    # Then search
    response = client.post("/vault/search", json={
        "query": "gear teeth mechanical",
        "project_root": str(tmp_project),
    })
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert len(data["results"]) >= 1
