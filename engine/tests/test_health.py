"""Tests for the health endpoint."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from cadforge_engine.app import create_app


@pytest.fixture
def client() -> TestClient:
    app = create_app()
    return TestClient(app)


def test_health_returns_ok(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "version" in data
    assert isinstance(data["capabilities"], list)


def test_health_version_matches(client: TestClient) -> None:
    from cadforge_engine import __version__
    response = client.get("/health")
    assert response.json()["version"] == __version__
