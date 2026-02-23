"""Tests for the design-then-code pipeline.

Uses mocked LLM calls to verify the 3-round loop logic.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
import pytest_asyncio

from cadforge_engine.agent.pipeline import run_design_pipeline


class MockLLMClient:
    """Mock LLM client that returns predetermined responses."""

    def __init__(self, responses: list[dict[str, Any]]) -> None:
        self._responses = list(responses)
        self._call_index = 0
        self.model = "mock-model"
        self.max_tokens = 8192

    def call(
        self,
        messages: list[dict[str, Any]],
        system: str,
        tools: list[dict[str, Any]],
    ) -> dict[str, Any]:
        if self._call_index >= len(self._responses):
            return {
                "content": [{"type": "text", "text": "APPROVED"}],
                "stop_reason": "end_turn",
                "usage": {"input_tokens": 0, "output_tokens": 0},
            }
        resp = self._responses[self._call_index]
        self._call_index += 1
        return resp


def _text_response(text: str) -> dict[str, Any]:
    return {
        "content": [{"type": "text", "text": text}],
        "stop_reason": "end_turn",
        "usage": {"input_tokens": 100, "output_tokens": 50},
    }


def _tool_use_response(code: str, output_name: str = "pipeline_model") -> dict[str, Any]:
    return {
        "content": [
            {"type": "text", "text": "Generating model..."},
            {
                "type": "tool_use",
                "id": "tool_001",
                "name": "ExecuteCadQuery",
                "input": {
                    "code": code,
                    "output_name": output_name,
                    "format": "stl",
                },
            },
        ],
        "stop_reason": "tool_use",
        "usage": {"input_tokens": 100, "output_tokens": 50},
    }


@pytest.mark.asyncio
async def test_pipeline_basic_flow(tmp_path: Path) -> None:
    """Test basic pipeline flow: designer → coder → renderer → judge (approved)."""
    mock_client = MockLLMClient([
        # 1. Designer response
        _text_response("Box: 20x15x10mm centered at origin"),
        # 2. Coder response (tool use)
        _tool_use_response(
            "import cadquery as cq\nresult = cq.Workplane('XY').box(20, 15, 10)"
        ),
        # 3. Coder follow-up (after tool result, no more tools)
        _text_response("Model created successfully."),
        # 4. Judge response (approved)
        _text_response("APPROVED"),
    ])

    events: list[dict[str, Any]] = []
    async for event in run_design_pipeline(
        llm_client=mock_client,
        prompt="Make a box 20x15x10mm",
        project_root=str(tmp_path),
        max_rounds=3,
    ):
        events.append(event)

    event_types = [e["event"] for e in events]
    assert "pipeline_step" in event_types
    assert "pipeline_round" in event_types
    assert "tool_use_start" in event_types
    assert "tool_result" in event_types
    assert "completion" in event_types
    assert "done" in event_types


@pytest.mark.asyncio
async def test_pipeline_revision_round(tmp_path: Path) -> None:
    """Test that judge feedback triggers a second coder round.

    Uses real CadQuery execution + real PyVista rendering with a mock
    LLM that rejects the first round then approves the second.
    """
    call_count = 0

    class RevisionMockClient:
        model = "mock"
        max_tokens = 8192

        def call(self, messages, system, tools):
            nonlocal call_count
            call_count += 1

            # Designer
            if "specification" in system.lower():
                return _text_response("Box: 10x10x10mm at origin")

            # Judge
            if "quality assurance" in system.lower() or "judge" in system.lower():
                # First judge call -> reject
                if call_count <= 5:
                    return _text_response("Needs revision: make it 20x20x20 instead.")
                # Second judge call -> approve
                return _text_response("APPROVED")

            # Coder — check if tools available
            if tools:
                return _tool_use_response(
                    "import cadquery as cq\nresult = cq.Workplane('XY').box(10, 10, 10)"
                )
            return _text_response("Model created.")

    events: list[dict[str, Any]] = []
    async for event in run_design_pipeline(
        llm_client=RevisionMockClient(),
        prompt="Make a box",
        project_root=str(tmp_path),
        max_rounds=3,
    ):
        events.append(event)

    event_types = [e["event"] for e in events]

    # Should see multiple rounds
    round_events = [e for e in events if e["event"] == "pipeline_round"]
    assert len(round_events) >= 2

    # Should have pipeline steps
    assert "pipeline_step" in event_types
    assert "completion" in event_types
    assert "done" in event_types


@pytest.mark.asyncio
async def test_pipeline_empty_spec(tmp_path: Path) -> None:
    """Test that empty designer spec ends pipeline gracefully."""
    mock_client = MockLLMClient([
        _text_response(""),
    ])

    events: list[dict[str, Any]] = []
    async for event in run_design_pipeline(
        llm_client=mock_client,
        prompt="???",
        project_root=str(tmp_path),
    ):
        events.append(event)

    event_types = [e["event"] for e in events]
    assert "completion" in event_types
    assert "done" in event_types


@pytest.mark.asyncio
async def test_pipeline_designer_error(tmp_path: Path) -> None:
    """Test pipeline handles LLM errors gracefully."""
    class ErrorClient:
        model = "error"
        max_tokens = 100

        def call(self, **kwargs):
            raise RuntimeError("API down")

    events: list[dict[str, Any]] = []
    async for event in run_design_pipeline(
        llm_client=ErrorClient(),
        prompt="Make something",
        project_root=str(tmp_path),
    ):
        events.append(event)

    event_types = [e["event"] for e in events]
    assert "completion" in event_types
    assert "done" in event_types
    # Should mention error
    completion = next(e for e in events if e["event"] == "completion")
    assert "error" in completion["data"]["text"].lower()
