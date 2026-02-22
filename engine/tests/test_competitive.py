"""Tests for competitive multi-agent pipeline."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from cadforge_engine.models.competitive import (
    CompetitiveDesignSpec,
    CompetitiveDesignStatus,
    CompetitiveDesignStore,
    CompetitiveRound,
    CritiqueRecord,
    FidelityScore,
    Proposal,
    ProposalStatus,
    SandboxEvaluation,
)
from cadforge_engine.agent.competitive import (
    _extract_json,
    _extract_text,
    run_competitive_pipeline,
)


# ---------------------------------------------------------------------------
# Test data models
# ---------------------------------------------------------------------------


class TestCompetitiveModels:
    def test_proposal_defaults(self):
        p = Proposal(model="test/model")
        assert p.status == ProposalStatus.PENDING
        assert p.code == ""
        assert p.critiques_received == []
        assert len(p.id) == 12

    def test_competitive_design_spec(self):
        spec = CompetitiveDesignSpec(
            title="Test Design",
            prompt="Make a box",
        )
        assert spec.status == CompetitiveDesignStatus.DRAFT
        assert spec.rounds == []
        assert spec.final_code is None

    def test_fidelity_score_threshold(self):
        fs = FidelityScore(proposal_id="test", score=96, passed=True)
        assert fs.passed is True
        fs2 = FidelityScore(proposal_id="test2", score=80, passed=False)
        assert fs2.passed is False

    def test_sandbox_evaluation(self):
        se = SandboxEvaluation(
            proposal_id="test",
            execution_success=True,
            is_watertight=True,
            volume_mm3=1000.0,
        )
        assert se.execution_success is True
        assert se.volume_mm3 == 1000.0

    def test_critique_record(self):
        cr = CritiqueRecord(
            critic_model="model_a",
            target_proposal_id="prop_1",
            strengths=["good dimensions"],
            weaknesses=["missing fillet"],
        )
        assert cr.strengths == ["good dimensions"]
        assert cr.weaknesses == ["missing fillet"]


class TestCompetitiveDesignStore:
    def test_save_and_get(self, tmp_path: Path):
        store = CompetitiveDesignStore(tmp_path)
        design = CompetitiveDesignSpec(title="Test", prompt="Make a box")
        store.save(design)

        loaded = store.get(design.id)
        assert loaded is not None
        assert loaded.title == "Test"
        assert loaded.prompt == "Make a box"

    def test_get_nonexistent(self, tmp_path: Path):
        store = CompetitiveDesignStore(tmp_path)
        assert store.get("nonexistent") is None

    def test_list_all(self, tmp_path: Path):
        store = CompetitiveDesignStore(tmp_path)
        d1 = CompetitiveDesignSpec(title="First", prompt="p1")
        d2 = CompetitiveDesignSpec(title="Second", prompt="p2")
        store.save(d1)
        store.save(d2)

        all_designs = store.list_all()
        assert len(all_designs) == 2

    def test_save_with_rounds(self, tmp_path: Path):
        store = CompetitiveDesignStore(tmp_path)
        design = CompetitiveDesignSpec(title="Test", prompt="box")
        proposal = Proposal(model="test/model", code="result = 1")
        round_ = CompetitiveRound(round_number=1, proposals=[proposal])
        design.rounds.append(round_)
        store.save(design)

        loaded = store.get(design.id)
        assert loaded is not None
        assert len(loaded.rounds) == 1
        assert len(loaded.rounds[0].proposals) == 1
        assert loaded.rounds[0].proposals[0].code == "result = 1"


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


class TestExtractJson:
    def test_plain_json(self):
        result = _extract_json('{"key": "value"}')
        assert result == {"key": "value"}

    def test_json_in_code_fence(self):
        text = '```json\n{"key": "value"}\n```'
        result = _extract_json(text)
        assert result == {"key": "value"}

    def test_json_with_surrounding_text(self):
        text = 'Here is the result: {"score": 95, "reasoning": "good"} end.'
        result = _extract_json(text)
        assert result["score"] == 95

    def test_invalid_json(self):
        result = _extract_json("not json at all")
        assert result == {}


class TestExtractText:
    def test_text_blocks(self):
        response = {"content": [
            {"type": "text", "text": "Hello"},
            {"type": "text", "text": "World"},
        ]}
        assert _extract_text(response) == "Hello\nWorld"

    def test_no_text(self):
        response = {"content": [{"type": "tool_use", "name": "test"}]}
        assert _extract_text(response) == ""


# ---------------------------------------------------------------------------
# Test pipeline stages (mocked LLM calls)
# ---------------------------------------------------------------------------


def _mock_llm_response(text: str) -> dict[str, Any]:
    """Create a mock Anthropic-format LLM response."""
    return {
        "content": [{"type": "text", "text": text}],
        "stop_reason": "end_turn",
        "usage": {"input_tokens": 10, "output_tokens": 20},
    }


def _mock_tool_response(tool_name: str, tool_input: dict) -> dict[str, Any]:
    """Create a mock response with a tool call."""
    return {
        "content": [
            {"type": "text", "text": "Let me execute this."},
            {"type": "tool_use", "id": "call_123", "name": tool_name, "input": tool_input},
        ],
        "stop_reason": "tool_use",
        "usage": {"input_tokens": 10, "output_tokens": 20},
    }


class TestSupervisorParseSpec:
    @pytest.mark.asyncio
    async def test_supervisor_parses_spec(self, tmp_path: Path):
        """Supervisor should produce golden spec + key constraints."""
        store = CompetitiveDesignStore(tmp_path)
        design = CompetitiveDesignSpec(
            title="Test Box",
            prompt="Create a 50mm cube",
        )
        store.save(design)

        supervisor_response = _mock_llm_response(json.dumps({
            "golden_spec": "A cube measuring 50mm on each side",
            "key_constraints": ["exact 50mm dimensions", "sharp edges"],
            "critical_dimensions": {"side_length": "50mm"},
            "manufacturing_notes": "Simple geometry, no supports needed",
        }))

        config = {
            "supervisor": {"model": "test/supervisor"},
            "judge": {"model": "test/judge"},
            "merger": {"model": "test/merger"},
            "proposal_agents": [{"model": "test/coder1"}],
            "fidelity_threshold": 95,
            "debate_enabled": False,
        }

        events = []
        with patch("cadforge_engine.agent.competitive.LiteLLMSubagentClient") as MockClient:
            instance = MagicMock()
            instance.model = "test/supervisor"
            instance.acall = AsyncMock(return_value=supervisor_response)
            MockClient.return_value = instance

            # Mock the coder to return immediately (no tool calls = empty code)
            async for event in run_competitive_pipeline(
                design=design, store=store, project_root=tmp_path,
                pipeline_config=config, max_rounds=1,
            ):
                events.append(event)

        # Should have supervisor events
        supervisor_events = [e for e in events if e["event"] == "competitive_supervisor"]
        assert len(supervisor_events) >= 1


class TestParallelProposals:
    @pytest.mark.asyncio
    async def test_partial_failure_tolerated(self, tmp_path: Path):
        """If some proposals fail, pipeline should continue with valid ones."""
        store = CompetitiveDesignStore(tmp_path)
        design = CompetitiveDesignSpec(
            title="Test", prompt="Make a box",
            specification="A 50mm cube",
        )
        store.save(design)

        call_count = 0

        async def mock_acall(messages, system, tools):
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                # Supervisor + first proposal succeed
                if "supervisor" in system.lower():
                    return _mock_llm_response(json.dumps({
                        "golden_spec": "50mm cube",
                        "key_constraints": [],
                    }))
                # Coder returns no tool calls (will be marked as failed)
                return _mock_llm_response("Here is my code: result = cq.Workplane().box(50,50,50)")
            # Other calls
            return _mock_llm_response("test response")

        config = {
            "supervisor": {"model": "test/sup"},
            "judge": {"model": "test/judge"},
            "merger": {"model": "test/merger"},
            "proposal_agents": [{"model": "test/a"}, {"model": "test/b"}],
            "fidelity_threshold": 50,
            "debate_enabled": False,
        }

        events = []
        with patch("cadforge_engine.agent.competitive.LiteLLMSubagentClient") as MockClient:
            mock = MagicMock()
            mock.model = "test/model"
            mock.acall = AsyncMock(side_effect=mock_acall)
            MockClient.return_value = mock

            async for event in run_competitive_pipeline(
                design=design, store=store, project_root=tmp_path,
                pipeline_config=config, max_rounds=1,
            ):
                events.append(event)

        # Should have proposal events
        proposal_events = [e for e in events if e["event"] == "competitive_proposal"]
        assert len(proposal_events) >= 2


class TestFidelityScoring:
    def test_score_threshold(self):
        """Scores >= threshold should pass."""
        fs = FidelityScore(proposal_id="p1", score=96, passed=True)
        assert fs.passed is True

        fs2 = FidelityScore(proposal_id="p2", score=80, passed=False)
        assert fs2.passed is False


class TestForcedRevert:
    @pytest.mark.asyncio
    async def test_forced_revert_on_low_score(self, tmp_path: Path):
        """All scores < threshold should trigger another round."""
        store = CompetitiveDesignStore(tmp_path)
        design = CompetitiveDesignSpec(
            title="Test", prompt="Make a box",
        )
        store.save(design)

        round_count = 0

        async def mock_acall(messages, system, tools):
            nonlocal round_count
            if "supervisor" in system.lower():
                return _mock_llm_response(json.dumps({
                    "golden_spec": "A cube",
                    "key_constraints": [],
                }))
            if "judge" in system.lower() or "fidelity" in system.lower():
                # Always give low score
                return _mock_llm_response(json.dumps({
                    "score": 50,
                    "text_similarity": 60,
                    "geometric_accuracy": 40,
                    "manufacturing_viability": 50,
                    "reasoning": "Needs improvement",
                }))
            # Coder returns text (no tool use)
            return _mock_llm_response("result = cq.Workplane().box(50,50,50)")

        config = {
            "supervisor": {"model": "test/sup"},
            "judge": {"model": "test/judge"},
            "merger": {"model": "test/merger"},
            "proposal_agents": [{"model": "test/a"}],
            "fidelity_threshold": 95,
            "debate_enabled": False,
        }

        events = []
        with patch("cadforge_engine.agent.competitive.LiteLLMSubagentClient") as MockClient:
            mock = MagicMock()
            mock.model = "test/model"
            mock.acall = AsyncMock(side_effect=mock_acall)
            MockClient.return_value = mock

            async for event in run_competitive_pipeline(
                design=design, store=store, project_root=tmp_path,
                pipeline_config=config, max_rounds=2,
            ):
                events.append(event)

        # Should have multiple rounds
        round_events = [e for e in events if e["event"] == "competitive_round"]
        assert len(round_events) >= 2

        # Should end in failure
        status_events = [e for e in events if e["event"] == "competitive_status"]
        final_status = [e for e in status_events if e["data"].get("status") == "failed"]
        assert len(final_status) >= 1


class TestMerger:
    @pytest.mark.asyncio
    async def test_merger_selects_winner(self, tmp_path: Path):
        """When one proposal passes, it should be selected."""
        store = CompetitiveDesignStore(tmp_path)
        design = CompetitiveDesignSpec(
            title="Test", prompt="Make a box",
        )
        store.save(design)

        async def mock_acall(messages, system, tools):
            if "supervisor" in system.lower():
                return _mock_llm_response(json.dumps({
                    "golden_spec": "A cube",
                    "key_constraints": [],
                }))
            if "judge" in system.lower() or "fidelity" in system.lower():
                return _mock_llm_response(json.dumps({
                    "score": 97,
                    "text_similarity": 95,
                    "geometric_accuracy": 98,
                    "manufacturing_viability": 97,
                    "reasoning": "Excellent",
                }))
            if "learner" in system.lower() or "pattern" in system.lower():
                return _mock_llm_response(json.dumps({
                    "patterns": [], "anti_patterns": [], "key_insights": [],
                }))
            # Coder
            return _mock_llm_response("result = cq.Workplane().box(50,50,50)")

        config = {
            "supervisor": {"model": "test/sup"},
            "judge": {"model": "test/judge"},
            "merger": {"model": "test/merger"},
            "proposal_agents": [{"model": "test/a"}],
            "fidelity_threshold": 95,
            "debate_enabled": False,
        }

        events = []
        with patch("cadforge_engine.agent.competitive.LiteLLMSubagentClient") as MockClient:
            mock = MagicMock()
            mock.model = "test/model"
            mock.acall = AsyncMock(side_effect=mock_acall)
            MockClient.return_value = mock

            # Mock learnings to avoid import errors (lazy imports in the function)
            with patch("cadforge_engine.vault.learnings.extract_learnings", return_value=[]):
                with patch("cadforge_engine.vault.indexer.index_chunks", return_value={}):
                    async for event in run_competitive_pipeline(
                        design=design, store=store, project_root=tmp_path,
                        pipeline_config=config, max_rounds=1,
                    ):
                        events.append(event)

        # Should complete successfully
        merger_events = [e for e in events if e["event"] == "competitive_merger"]
        completed = [e for e in merger_events if e["data"].get("status") == "completed"]
        assert len(completed) >= 1


class TestHumanApproval:
    @pytest.mark.asyncio
    async def test_pipeline_pauses_for_approval(self, tmp_path: Path):
        """Pipeline should pause and yield approval event."""
        store = CompetitiveDesignStore(tmp_path)
        design = CompetitiveDesignSpec(
            title="Test", prompt="Make a box",
        )
        store.save(design)

        async def mock_acall(messages, system, tools):
            if "supervisor" in system.lower():
                return _mock_llm_response(json.dumps({
                    "golden_spec": "A cube",
                    "key_constraints": [],
                }))
            if "judge" in system.lower() or "fidelity" in system.lower():
                return _mock_llm_response(json.dumps({
                    "score": 97,
                    "text_similarity": 95,
                    "geometric_accuracy": 98,
                    "manufacturing_viability": 97,
                    "reasoning": "Excellent",
                }))
            return _mock_llm_response("result = cq.Workplane().box(50,50,50)")

        config = {
            "supervisor": {"model": "test/sup"},
            "judge": {"model": "test/judge"},
            "merger": {"model": "test/merger"},
            "proposal_agents": [{"model": "test/a"}],
            "fidelity_threshold": 95,
            "debate_enabled": False,
            "human_approval_required": True,
        }

        events = []
        with patch("cadforge_engine.agent.competitive.LiteLLMSubagentClient") as MockClient:
            mock = MagicMock()
            mock.model = "test/model"
            mock.acall = AsyncMock(side_effect=mock_acall)
            MockClient.return_value = mock

            async for event in run_competitive_pipeline(
                design=design, store=store, project_root=tmp_path,
                pipeline_config=config, max_rounds=1,
            ):
                events.append(event)

        # Should have approval request event
        approval_events = [e for e in events if e["event"] == "competitive_approval_requested"]
        assert len(approval_events) == 1

        # Design status should be awaiting approval
        loaded = store.get(design.id)
        assert loaded is not None
        assert loaded.status == CompetitiveDesignStatus.AWAITING_APPROVAL
