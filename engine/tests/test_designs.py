"""Tests for the design spec model, store, and learning extraction."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import pytest_asyncio

from cadforge_engine.models.designs import (
    DesignSpec,
    DesignStatus,
    DesignStore,
    IterationRecord,
)
from cadforge_engine.vault.learnings import extract_learnings


# ── DesignSpec model tests ──


class TestDesignSpec:
    """Test the DesignSpec Pydantic model."""

    def test_default_values(self) -> None:
        spec = DesignSpec()
        assert len(spec.id) == 12
        assert spec.title == ""
        assert spec.prompt == ""
        assert spec.specification == ""
        assert spec.constraints == {}
        assert spec.status == DesignStatus.DRAFT
        assert spec.iterations == []
        assert spec.final_output_path is None
        assert spec.learnings_indexed is False
        assert spec.created_at is not None
        assert spec.updated_at is not None

    def test_status_enum(self) -> None:
        assert DesignStatus.DRAFT.value == "draft"
        assert DesignStatus.APPROVED.value == "approved"
        assert DesignStatus.EXECUTING.value == "executing"
        assert DesignStatus.COMPLETED.value == "completed"
        assert DesignStatus.FAILED.value == "failed"

    def test_with_iterations(self) -> None:
        it = IterationRecord(
            round_number=1,
            code="result = box(10, 10, 10)",
            stl_path="/tmp/model.stl",
            verdict="APPROVED",
            approved=True,
        )
        spec = DesignSpec(
            title="Test Box",
            prompt="Make a box",
            specification="Box 10mm cube",
            iterations=[it],
        )
        assert len(spec.iterations) == 1
        assert spec.iterations[0].approved is True

    def test_serialization_roundtrip(self) -> None:
        spec = DesignSpec(
            title="Test",
            prompt="Test prompt",
            specification="Spec text",
            constraints={"min_wall": 1.0},
        )
        data = json.loads(spec.model_dump_json())
        restored = DesignSpec(**data)
        assert restored.id == spec.id
        assert restored.title == spec.title
        assert restored.constraints == spec.constraints


class TestIterationRecord:
    """Test the IterationRecord model."""

    def test_defaults(self) -> None:
        it = IterationRecord(round_number=1)
        assert it.round_number == 1
        assert it.code == ""
        assert it.stl_path is None
        assert it.png_paths == []
        assert it.verdict == ""
        assert it.approved is False
        assert it.errors == []
        assert it.timestamp is not None

    def test_with_errors(self) -> None:
        it = IterationRecord(
            round_number=2,
            code="bad code",
            errors=["SyntaxError", "NameError"],
        )
        assert len(it.errors) == 2


# ── DesignStore persistence tests ──


class TestDesignStore:
    """Test file-based design persistence."""

    def test_save_and_get(self, tmp_path: Path) -> None:
        store = DesignStore(tmp_path)
        spec = DesignSpec(title="Box", prompt="Make a box")
        store.save(spec)

        loaded = store.get(spec.id)
        assert loaded is not None
        assert loaded.id == spec.id
        assert loaded.title == "Box"

    def test_get_missing(self, tmp_path: Path) -> None:
        store = DesignStore(tmp_path)
        assert store.get("nonexistent") is None

    def test_list_all(self, tmp_path: Path) -> None:
        store = DesignStore(tmp_path)
        store.save(DesignSpec(title="A"))
        store.save(DesignSpec(title="B"))
        all_designs = store.list_all()
        assert len(all_designs) == 2

    def test_delete(self, tmp_path: Path) -> None:
        store = DesignStore(tmp_path)
        spec = DesignSpec(title="Deletable")
        store.save(spec)
        assert store.delete(spec.id) is True
        assert store.get(spec.id) is None

    def test_delete_missing(self, tmp_path: Path) -> None:
        store = DesignStore(tmp_path)
        assert store.delete("nonexistent") is False

    def test_persistence_with_iterations(self, tmp_path: Path) -> None:
        store = DesignStore(tmp_path)
        spec = DesignSpec(title="Iter test", prompt="Test")
        it = IterationRecord(
            round_number=1,
            code="result = box(10)",
            stl_path="/tmp/out.stl",
            png_paths=["/tmp/front.png", "/tmp/side.png"],
            verdict="APPROVED",
            approved=True,
        )
        spec.iterations.append(it)
        spec.status = DesignStatus.COMPLETED
        store.save(spec)

        loaded = store.get(spec.id)
        assert loaded is not None
        assert len(loaded.iterations) == 1
        assert loaded.iterations[0].round_number == 1
        assert loaded.iterations[0].approved is True
        assert loaded.iterations[0].png_paths == ["/tmp/front.png", "/tmp/side.png"]
        assert loaded.status == DesignStatus.COMPLETED

    def test_updated_at_changes(self, tmp_path: Path) -> None:
        store = DesignStore(tmp_path)
        spec = DesignSpec(title="Timestamp test")
        store.save(spec)
        first_updated = spec.updated_at

        spec.title = "Changed"
        store.save(spec)
        assert spec.updated_at >= first_updated

    def test_file_is_json(self, tmp_path: Path) -> None:
        store = DesignStore(tmp_path)
        spec = DesignSpec(title="JSON test")
        store.save(spec)

        json_path = tmp_path / ".cadforge" / "designs" / f"{spec.id}.json"
        assert json_path.exists()
        data = json.loads(json_path.read_text())
        assert data["title"] == "JSON test"


# ── Learning extraction tests ──


class TestLearningExtraction:
    """Test extract_learnings from completed designs."""

    def _make_completed_design(self) -> DesignSpec:
        """Build a design with a failed round then an approved round."""
        design = DesignSpec(
            title="Test Bracket",
            prompt="Create a bracket with mounting holes",
            specification="L-shaped bracket, 50x30x3mm base, 30x30x3mm upright, 4mm mounting holes",
            status=DesignStatus.COMPLETED,
        )
        # Round 1: failed with error
        design.iterations.append(IterationRecord(
            round_number=1,
            code="result = cq.Workplane('XY').box(50, 30, 3)",
            errors=["NameError: cq not defined"],
            verdict="",
            approved=False,
        ))
        # Round 2: failed with judge feedback
        design.iterations.append(IterationRecord(
            round_number=2,
            code="import cadquery as cq\nresult = cq.Workplane('XY').box(50, 30, 3)",
            stl_path="/tmp/bracket.stl",
            png_paths=["/tmp/bracket_front.png"],
            verdict="Missing the upright portion and mounting holes.",
            approved=False,
        ))
        # Round 3: approved
        design.iterations.append(IterationRecord(
            round_number=3,
            code=(
                "import cadquery as cq\n"
                "base = cq.Workplane('XY').box(50, 30, 3)\n"
                "upright = cq.Workplane('XZ').center(0, 15).box(30, 30, 3)\n"
                "result = base.union(upright)"
            ),
            stl_path="/tmp/bracket_v3.stl",
            png_paths=["/tmp/bracket_v3_front.png", "/tmp/bracket_v3_side.png"],
            verdict="APPROVED",
            approved=True,
        ))
        return design

    def test_extracts_successful_pattern(self) -> None:
        design = self._make_completed_design()
        chunks = extract_learnings(design)

        successful = [c for c in chunks if "successful" in c.tags]
        assert len(successful) == 1
        assert "cad-pattern" in successful[0].tags
        assert "learning" in successful[0].tags
        assert "bracket" in successful[0].content.lower()

    def test_extracts_error_patterns(self) -> None:
        design = self._make_completed_design()
        chunks = extract_learnings(design)

        errors = [c for c in chunks if "error-pattern" in c.tags]
        assert len(errors) == 1  # Only round 1 has errors
        assert "NameError" in errors[0].content

    def test_extracts_refinement_feedback(self) -> None:
        design = self._make_completed_design()
        chunks = extract_learnings(design)

        refinements = [c for c in chunks if "refinement" in c.tags]
        assert len(refinements) == 1  # Round 2 has verdict but no approval
        assert "mounting holes" in refinements[0].content.lower()

    def test_extracts_geometric_pattern(self) -> None:
        design = self._make_completed_design()
        chunks = extract_learnings(design)

        geometric = [c for c in chunks if "geometric-pattern" in c.tags]
        assert len(geometric) == 1
        assert "bracket" in geometric[0].content.lower()

    def test_total_chunk_count(self) -> None:
        design = self._make_completed_design()
        chunks = extract_learnings(design)
        # 1 successful + 1 error + 1 refinement + 1 geometric = 4
        assert len(chunks) == 4

    def test_chunk_metadata(self) -> None:
        design = self._make_completed_design()
        chunks = extract_learnings(design)

        for chunk in chunks:
            assert chunk.metadata.get("design_id") == design.id
            assert chunk.metadata.get("learning_type") is not None
            assert chunk.file_path == f"learnings/design-{design.id}.md"

    def test_empty_design_no_learnings(self) -> None:
        design = DesignSpec(title="Empty", prompt="Nothing")
        chunks = extract_learnings(design)
        assert chunks == []

    def test_failed_only_design(self) -> None:
        """A design with only failed iterations should still produce error learnings."""
        design = DesignSpec(
            title="Failed",
            prompt="Make something",
            specification="A thing",
            status=DesignStatus.FAILED,
        )
        design.iterations.append(IterationRecord(
            round_number=1,
            code="bad_code()",
            errors=["SyntaxError"],
            approved=False,
        ))
        chunks = extract_learnings(design)
        # Should get error pattern but no successful/geometric
        error_chunks = [c for c in chunks if "error-pattern" in c.tags]
        successful_chunks = [c for c in chunks if "successful" in c.tags]
        assert len(error_chunks) == 1
        assert len(successful_chunks) == 0


# ── Tracked pipeline tests (mock LLM) ──


class MockLLMClient:
    """Mock LLM client for tracked pipeline tests."""

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


def _tool_use_response(code: str) -> dict[str, Any]:
    return {
        "content": [
            {"type": "text", "text": "Generating model..."},
            {
                "type": "tool_use",
                "id": "tool_001",
                "name": "ExecuteCadQuery",
                "input": {
                    "code": code,
                    "output_name": "design_model",
                    "format": "stl",
                },
            },
        ],
        "stop_reason": "tool_use",
        "usage": {"input_tokens": 100, "output_tokens": 50},
    }


@pytest.mark.asyncio
async def test_tracked_pipeline_persists_iterations(tmp_path: Path) -> None:
    """Test that tracked pipeline persists IterationRecords to the DesignStore."""
    from cadforge_engine.agent.pipeline import run_design_pipeline_tracked

    store = DesignStore(tmp_path)
    design = DesignSpec(
        title="Tracked Box",
        prompt="Make a box",
        specification="Box: 20x15x10mm centered at origin",
        status=DesignStatus.APPROVED,
    )
    store.save(design)

    mock_client = MockLLMClient([
        # Coder: tool use
        _tool_use_response("import cadquery as cq\nresult = cq.Workplane('XY').box(20, 15, 10)"),
        # Coder follow-up: done
        _text_response("Model created."),
        # Judge: APPROVED
        _text_response("APPROVED"),
    ])

    events: list[dict[str, Any]] = []
    async for event in run_design_pipeline_tracked(
        llm_client=mock_client,
        design=design,
        design_store=store,
        project_root=tmp_path,
        max_rounds=3,
    ):
        events.append(event)

    event_types = [e["event"] for e in events]
    assert "iteration_saved" in event_types
    assert "design_updated" in event_types
    assert "completion" in event_types
    assert "done" in event_types

    # Reload from disk and check
    reloaded = store.get(design.id)
    assert reloaded is not None
    assert len(reloaded.iterations) >= 1
    assert reloaded.status in (DesignStatus.COMPLETED, DesignStatus.FAILED)


@pytest.mark.asyncio
async def test_tracked_pipeline_empty_spec(tmp_path: Path) -> None:
    """Test that tracked pipeline handles empty spec gracefully."""
    from cadforge_engine.agent.pipeline import run_design_pipeline_tracked

    store = DesignStore(tmp_path)
    design = DesignSpec(title="Empty", specification="")
    store.save(design)

    mock_client = MockLLMClient([])

    events: list[dict[str, Any]] = []
    async for event in run_design_pipeline_tracked(
        llm_client=mock_client,
        design=design,
        design_store=store,
        project_root=tmp_path,
    ):
        events.append(event)

    event_types = [e["event"] for e in events]
    assert "completion" in event_types
    assert "done" in event_types


@pytest.mark.asyncio
async def test_tracked_pipeline_resume_context(tmp_path: Path) -> None:
    """Test that resume builds context from previous iterations."""
    from cadforge_engine.agent.pipeline import _build_resume_context

    design = DesignSpec(title="Resume test", specification="A box")
    design.iterations.append(IterationRecord(
        round_number=1,
        code="bad_code()",
        errors=["NameError: bad_code"],
        approved=False,
    ))
    design.iterations.append(IterationRecord(
        round_number=2,
        code="result = box(10)",
        verdict="Dimensions too small",
        approved=False,
    ))

    ctx = _build_resume_context(design)
    assert "Previous attempts:" in ctx
    assert "Round 1" in ctx
    assert "Round 2" in ctx
    assert "bad_code" in ctx
