"""Tests for the CAD subagent SSE endpoint.

These tests verify the SSE endpoint format and error handling
without requiring actual Anthropic API credentials.
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


def test_subagent_endpoint_reachable(client: TestClient, tmp_path: Path) -> None:
    """Test that the /subagent/cad endpoint is registered and reachable."""
    response = client.post("/subagent/cad", json={
        "prompt": "Create a box",
        "context": "",
        "project_root": str(tmp_path),
        "auth": {},
        "model": "claude-sonnet-4-5-20250929",
        "max_tokens": 8192,
    })
    # Should return 200 with SSE stream (not 404/405)
    assert response.status_code == 200


def test_subagent_missing_auth_returns_error(client: TestClient, tmp_path: Path) -> None:
    """Test that missing auth credentials produce a graceful error in SSE format."""
    response = client.post("/subagent/cad", json={
        "prompt": "Create a box",
        "context": "",
        "project_root": str(tmp_path),
        "auth": {},
    })
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")

    # Parse SSE events from the response body
    body = response.text
    events = _parse_sse_events(body)

    # Should contain a completion event with error message
    completion_events = [e for e in events if e["event"] == "completion"]
    assert len(completion_events) >= 1
    assert "No auth" in completion_events[0]["data"].get("text", "")

    # Should end with a done event
    done_events = [e for e in events if e["event"] == "done"]
    assert len(done_events) >= 1


def test_subagent_sse_format(client: TestClient, tmp_path: Path) -> None:
    """Test that the SSE wire format is correct (event: + data: + blank line)."""
    response = client.post("/subagent/cad", json={
        "prompt": "Create a box",
        "project_root": str(tmp_path),
        "auth": {},
    })
    body = response.text

    # SSE events should follow the format: "event: <type>\ndata: <json>\n\n"
    lines = body.split("\n")
    i = 0
    event_count = 0
    while i < len(lines):
        if lines[i].startswith("event: "):
            event_type = lines[i][7:]
            assert event_type in ("status", "text_delta", "tool_use_start", "tool_result", "completion", "done")
            i += 1
            if i < len(lines):
                assert lines[i].startswith("data: "), f"Expected 'data: ' line after event line, got: {lines[i]}"
                # Verify data is valid JSON
                import json
                json.loads(lines[i][6:])
                i += 1
            event_count += 1
        else:
            i += 1

    assert event_count >= 2  # At least completion + done


def test_subagent_request_validation(client: TestClient) -> None:
    """Test that the endpoint validates required fields."""
    # Missing required 'prompt' field
    response = client.post("/subagent/cad", json={
        "project_root": "/tmp",
        "auth": {},
    })
    assert response.status_code == 422  # Pydantic validation error


def _parse_sse_events(body: str) -> list[dict]:
    """Parse SSE events from response body."""
    import json

    events = []
    lines = body.split("\n")
    current_event = ""
    current_data = ""

    for line in lines:
        if line.startswith("event: "):
            current_event = line[7:].strip()
        elif line.startswith("data: "):
            current_data = line[6:]
        elif line == "" and current_event:
            try:
                data = json.loads(current_data)
            except json.JSONDecodeError:
                data = {}
            events.append({"event": current_event, "data": data})
            current_event = ""
            current_data = ""

    return events
