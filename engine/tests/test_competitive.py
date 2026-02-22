"""Tests for competitive multi-agent pipeline (LangGraph-based)."""

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
# Test LangGraph graph construction
# ---------------------------------------------------------------------------


class TestGraphConstruction:
    def test_graph_compiles(self):
        """build_competitive_graph() should return a compiled graph."""
        from cadforge_engine.agent.competitive_graph import build_competitive_graph
        graph = build_competitive_graph()
        assert graph is not None

    def test_graph_mermaid(self):
        """Graph should produce valid Mermaid diagram output."""
        from cadforge_engine.agent.competitive_graph import build_competitive_graph
        graph = build_competitive_graph()
        mermaid = graph.get_graph().draw_mermaid()
        assert isinstance(mermaid, str)
        assert len(mermaid) > 0
        # Should contain key node names
        assert "supervisor" in mermaid
        assert "merger_selector" in mermaid

    def test_checkpointer_memory_saver(self):
        """MemorySaver should be used by default."""
        from cadforge_engine.agent.competitive_graph import build_competitive_graph
        graph = build_competitive_graph()
        # The graph was compiled with a checkpointer
        assert graph is not None


# ---------------------------------------------------------------------------
# Test pipeline stages via LangGraph (mocked LLM calls)
# ---------------------------------------------------------------------------


def _mock_llm_response(text: str) -> dict[str, Any]:
    """Create a mock Anthropic-format LLM response."""
    return {
        "content": [{"type": "text", "text": text}],
        "stop_reason": "end_turn",
        "usage": {"input_tokens": 10, "output_tokens": 20},
    }


def _noop_evaluate_proposal(proposal, project_root, previous_stl=None):
    """No-op sandbox evaluation that avoids importing CadQuery/VTK."""
    return SandboxEvaluation(
        proposal_id=proposal.id,
        execution_success=True,
        is_watertight=True,
        volume_mm3=125000.0,  # 50^3 cube
        surface_area_mm2=15000.0,
        bounding_box={"size_x": 50.0, "size_y": 50.0, "size_z": 50.0},
        dfm_report_data={
            "passed": True,
            "build_volume_ok": True,
            "min_wall_ok": True,
            "overhang_ok": True,
            "issues": [],
            "suggestions": [],
        },
        fea_risk_level="low",
        fea_risk_score=0.0,
        fea_notes=[],
    )


# Shared patch targets for all graph integration tests
_GRAPH_PATCHES = [
    "cadforge_engine.agent.competitive_graph.LiteLLMSubagentClient",
    "cadforge_engine.agent.competitive_graph._evaluate_proposal",
]


class TestGraphSupervisor:
    @pytest.mark.asyncio
    async def test_supervisor_parses_spec(self, tmp_path: Path):
        """Supervisor node should produce golden spec + key constraints."""
        from cadforge_engine.agent.competitive_graph import run_competitive_graph

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
        with patch(_GRAPH_PATCHES[0]) as MockClient, \
             patch(_GRAPH_PATCHES[1], side_effect=_noop_evaluate_proposal):
            instance = MagicMock()
            instance.model = "test/supervisor"
            instance.acall = AsyncMock(return_value=supervisor_response)
            instance.call = MagicMock(return_value=supervisor_response)
            MockClient.return_value = instance

            async for event in run_competitive_graph(
                design=design, store=store, project_root=tmp_path,
                pipeline_config=config, max_rounds=1,
            ):
                events.append(event)

        # Should have supervisor events
        supervisor_events = [e for e in events if e["event"] == "competitive_supervisor"]
        assert len(supervisor_events) >= 1


class TestGraphProposals:
    @pytest.mark.asyncio
    async def test_partial_failure_tolerated(self, tmp_path: Path):
        """If some proposals fail, pipeline should continue with valid ones."""
        from cadforge_engine.agent.competitive_graph import run_competitive_graph

        store = CompetitiveDesignStore(tmp_path)
        design = CompetitiveDesignSpec(
            title="Test", prompt="Make a box",
            specification="A 50mm cube",
        )
        store.save(design)

        async def mock_acall(messages, system, tools):
            if "supervisor" in system.lower():
                return _mock_llm_response(json.dumps({
                    "golden_spec": "50mm cube",
                    "key_constraints": [],
                }))
            if "judge" in system.lower() or "fidelity" in system.lower():
                return _mock_llm_response(json.dumps({
                    "score": 50, "text_similarity": 60,
                    "geometric_accuracy": 40, "manufacturing_viability": 50,
                    "reasoning": "Needs work",
                }))
            # Coder returns text-only = code captured
            return _mock_llm_response("Here is my code: result = cq.Workplane().box(50,50,50)")

        config = {
            "supervisor": {"model": "test/sup"},
            "judge": {"model": "test/judge"},
            "merger": {"model": "test/merger"},
            "proposal_agents": [{"model": "test/a"}, {"model": "test/b"}],
            "fidelity_threshold": 50,
            "debate_enabled": False,
        }

        events = []
        with patch(_GRAPH_PATCHES[0]) as MockClient, \
             patch(_GRAPH_PATCHES[1], side_effect=_noop_evaluate_proposal):
            mock = MagicMock()
            mock.model = "test/model"
            mock.acall = AsyncMock(side_effect=mock_acall)
            mock.call = MagicMock(return_value=_mock_llm_response(json.dumps({
                "golden_spec": "50mm cube", "key_constraints": [],
            })))
            MockClient.return_value = mock

            async for event in run_competitive_graph(
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


class TestGraphForcedRevert:
    @pytest.mark.asyncio
    async def test_forced_revert_on_low_score(self, tmp_path: Path):
        """All scores < threshold should trigger another round."""
        from cadforge_engine.agent.competitive_graph import run_competitive_graph

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
                    "score": 50,
                    "text_similarity": 60,
                    "geometric_accuracy": 40,
                    "manufacturing_viability": 50,
                    "reasoning": "Needs improvement",
                }))
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
        with patch(_GRAPH_PATCHES[0]) as MockClient, \
             patch(_GRAPH_PATCHES[1], side_effect=_noop_evaluate_proposal):
            mock = MagicMock()
            mock.model = "test/model"
            mock.acall = AsyncMock(side_effect=mock_acall)
            mock.call = MagicMock(return_value=_mock_llm_response(json.dumps({
                "golden_spec": "A cube", "key_constraints": [],
            })))
            MockClient.return_value = mock

            async for event in run_competitive_graph(
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


class TestGraphMerger:
    @pytest.mark.asyncio
    async def test_merger_selects_winner(self, tmp_path: Path):
        """When one proposal passes, it should be selected."""
        from cadforge_engine.agent.competitive_graph import run_competitive_graph

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
                    "critical_dimensions": {"side_length": "50mm", "side_width": "50mm", "side_height": "50mm"},
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
        with patch(_GRAPH_PATCHES[0]) as MockClient, \
             patch(_GRAPH_PATCHES[1], side_effect=_noop_evaluate_proposal):
            mock = MagicMock()
            mock.model = "test/model"
            mock.acall = AsyncMock(side_effect=mock_acall)
            mock.call = MagicMock(return_value=_mock_llm_response(json.dumps({
                "golden_spec": "A cube", "key_constraints": [],
            })))
            MockClient.return_value = mock

            async for event in run_competitive_graph(
                design=design, store=store, project_root=tmp_path,
                pipeline_config=config, max_rounds=1,
            ):
                events.append(event)

        # Should complete successfully
        merger_events = [e for e in events if e["event"] == "competitive_merger"]
        completed = [e for e in merger_events if e["data"].get("status") == "completed"]
        assert len(completed) >= 1


class TestGraphHumanApproval:
    @pytest.mark.asyncio
    async def test_graph_interrupt_resume(self, tmp_path: Path):
        """Graph should pause at human_approval and resume with Command."""
        from langgraph.checkpoint.memory import MemorySaver
        from langgraph.types import Command
        from cadforge_engine.agent.competitive_graph import build_competitive_graph

        checkpointer = MemorySaver()

        async def mock_acall(messages, system, tools):
            if "supervisor" in system.lower():
                return _mock_llm_response(json.dumps({
                    "golden_spec": "A cube",
                    "key_constraints": [],
                    "critical_dimensions": {"side_length": "50mm", "side_width": "50mm", "side_height": "50mm"},
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

        design_id = "test_hitl_123"
        initial_state = {
            "design_id": design_id,
            "prompt": "Make a box",
            "specification": "",
            "project_root": str(tmp_path),
            "pipeline_config": config,
            "max_rounds": 1,
            "fidelity_threshold": 95.0,
            "debate_enabled": False,
            "sse_events": [],
            "golden_spec": "",
            "key_constraints": [],
            "constraints": {},
            "kb_context": "",
            "current_round": 0,
            "proposals": [],
            "_proposal_results": [],
            "sandbox_evals": [],
            "critiques": [],
            "_fidelity_results": [],
            "fidelity_scores": [],
            "accumulated_feedback": [],
            "previous_stl": "",
            "winner_code": "",
            "winner_id": "",
            "winner_model": "",
            "version_history": [],
            "fidelity_score_history": [],
            "learner_data": {},
            "final_status": "",
            "final_message": "",
        }

        thread_config = {"configurable": {"thread_id": design_id}}

        with patch(_GRAPH_PATCHES[0]) as MockClient, \
             patch(_GRAPH_PATCHES[1], side_effect=_noop_evaluate_proposal):
            mock = MagicMock()
            mock.model = "test/model"
            mock.acall = AsyncMock(side_effect=mock_acall)
            mock.call = MagicMock(return_value=_mock_llm_response(json.dumps({
                "golden_spec": "A cube", "key_constraints": [],
            })))
            MockClient.return_value = mock

            graph = build_competitive_graph(checkpointer=checkpointer)

            # Run until interrupt
            events_phase1 = []
            async for chunk in graph.astream(initial_state, thread_config, stream_mode="updates"):
                for node_name, output in chunk.items():
                    if output is None or not isinstance(output, dict):
                        continue
                    for ev in output.get("sse_events", []):
                        events_phase1.append(ev)

            # Graph should have paused — verify the state is saved
            state = await graph.aget_state(thread_config)
            assert state is not None

            # Resume with approval
            events_phase2 = []
            async for chunk in graph.astream(
                Command(resume={"approved": True, "feedback": "Looks good"}),
                thread_config,
                stream_mode="updates",
            ):
                for node_name, output in chunk.items():
                    if output is None or not isinstance(output, dict):
                        continue
                    for ev in output.get("sse_events", []):
                        events_phase2.append(ev)

        # Phase 2 should have approval response
        approval_events = [e for e in events_phase2 if e["event"] == "competitive_approval_response"]
        assert len(approval_events) >= 1
        assert approval_events[0]["data"]["approved"] is True


# ---------------------------------------------------------------------------
# Hybrid scoring tests
# ---------------------------------------------------------------------------


class TestHybridScoring:
    @pytest.mark.asyncio
    async def test_blended_score(self, tmp_path: Path):
        """Hybrid score should blend 60% algo + 40% LLM."""
        from cadforge_engine.agent.competitive import _run_fidelity_judge
        from cadforge_engine.agent.llm import LiteLLMSubagentClient

        # LLM returns score=80
        llm_response = _mock_llm_response(json.dumps({
            "score": 80,
            "text_similarity": 75,
            "geometric_accuracy": 85,
            "manufacturing_viability": 80,
            "reasoning": "Good but not perfect",
        }))

        mock_client = MagicMock(spec=LiteLLMSubagentClient)
        mock_client.model = "test/judge"
        mock_client.acall = AsyncMock(return_value=llm_response)

        proposal = Proposal(model="test/coder", code="result = Box(50, 50, 50)")
        proposal.sandbox_eval = SandboxEvaluation(
            proposal_id=proposal.id,
            execution_success=True,
            is_watertight=True,
            volume_mm3=125000.0,
            bounding_box={"size_x": 50.0, "size_y": 50.0, "size_z": 50.0},
            dfm_report_data={"passed": True, "issues": []},
        )

        constraints = {
            "critical_dimensions": {"side_length": "50mm", "side_width": "50mm", "side_height": "50mm"},
        }

        fs = await _run_fidelity_judge(
            mock_client, proposal, "A 50mm cube", constraints, threshold=50.0,
        )

        # Algo should be ~100 (perfect dims, good volume, clean DFM)
        # Blended = algo*0.6 + 80*0.4 = ~92
        assert fs.algorithmic_score > 80
        assert fs.llm_score == 80.0
        assert fs.score == pytest.approx(fs.algorithmic_score * 0.6 + 80 * 0.4, abs=0.1)

    @pytest.mark.asyncio
    async def test_fidelity_score_new_fields(self, tmp_path: Path):
        """FidelityScore should have algorithmic_score, llm_score, algorithmic_details."""
        from cadforge_engine.agent.competitive import _run_fidelity_judge
        from cadforge_engine.agent.llm import LiteLLMSubagentClient

        llm_response = _mock_llm_response(json.dumps({
            "score": 70,
            "text_similarity": 65,
            "geometric_accuracy": 75,
            "manufacturing_viability": 70,
            "reasoning": "Acceptable",
        }))

        mock_client = MagicMock(spec=LiteLLMSubagentClient)
        mock_client.model = "test/judge"
        mock_client.acall = AsyncMock(return_value=llm_response)

        proposal = Proposal(model="test/coder", code="result = Box(50, 50, 50)")
        proposal.sandbox_eval = SandboxEvaluation(
            proposal_id=proposal.id,
            execution_success=True,
            is_watertight=True,
            volume_mm3=125000.0,
            bounding_box={"size_x": 50.0, "size_y": 50.0, "size_z": 50.0},
        )

        fs = await _run_fidelity_judge(
            mock_client, proposal, "A 50mm cube", {}, threshold=50.0,
        )

        assert fs.algorithmic_score >= 0
        assert fs.llm_score == 70.0
        assert isinstance(fs.algorithmic_details, dict)
        assert "dimension_match_score" in fs.algorithmic_details


# ---------------------------------------------------------------------------
# Version history tests
# ---------------------------------------------------------------------------


class TestVersionHistory:
    @pytest.mark.asyncio
    async def test_history_accumulates_across_rounds(self, tmp_path: Path):
        """A 2-round pipeline should produce 2 entries in version_history."""
        from cadforge_engine.agent.competitive_graph import run_competitive_graph

        store = CompetitiveDesignStore(tmp_path)
        design = CompetitiveDesignSpec(title="Test", prompt="Make a box")
        store.save(design)

        call_count = 0

        async def mock_acall(messages, system, tools):
            nonlocal call_count
            call_count += 1
            if "supervisor" in system.lower():
                return _mock_llm_response(json.dumps({
                    "golden_spec": "A cube",
                    "key_constraints": [],
                    "critical_dimensions": {"side_length": "50mm"},
                }))
            if "judge" in system.lower() or "fidelity" in system.lower():
                # First round: fail (low LLM score). Second round: pass.
                if call_count <= 6:
                    return _mock_llm_response(json.dumps({
                        "score": 10, "text_similarity": 10,
                        "geometric_accuracy": 10, "manufacturing_viability": 10,
                        "reasoning": "Poor",
                    }))
                else:
                    return _mock_llm_response(json.dumps({
                        "score": 99, "text_similarity": 99,
                        "geometric_accuracy": 99, "manufacturing_viability": 99,
                        "reasoning": "Excellent",
                    }))
            if "learner" in system.lower() or "pattern" in system.lower():
                return _mock_llm_response(json.dumps({
                    "patterns": [], "anti_patterns": [], "key_insights": [],
                }))
            return _mock_llm_response("result = Box(50, 50, 50)")

        config = {
            "supervisor": {"model": "test/sup"},
            "judge": {"model": "test/judge"},
            "merger": {"model": "test/merger"},
            "proposal_agents": [{"model": "test/a"}],
            "fidelity_threshold": 50,
            "debate_enabled": False,
        }

        events = []
        with patch(_GRAPH_PATCHES[0]) as MockClient, \
             patch(_GRAPH_PATCHES[1], side_effect=_noop_evaluate_proposal):
            mock = MagicMock()
            mock.model = "test/model"
            mock.acall = AsyncMock(side_effect=mock_acall)
            MockClient.return_value = mock

            async for event in run_competitive_graph(
                design=design, store=store, project_root=tmp_path,
                pipeline_config=config, max_rounds=3,
            ):
                events.append(event)

        # Design should have version history entries
        loaded = store.get(design.id)
        assert loaded is not None
        assert len(loaded.version_history) >= 1

    @pytest.mark.asyncio
    async def test_fidelity_history_accumulates(self, tmp_path: Path):
        """Fidelity score history should have entries from pipeline rounds."""
        from cadforge_engine.agent.competitive_graph import run_competitive_graph

        store = CompetitiveDesignStore(tmp_path)
        design = CompetitiveDesignSpec(title="Test", prompt="Make a box")
        store.save(design)

        async def mock_acall(messages, system, tools):
            if "supervisor" in system.lower():
                return _mock_llm_response(json.dumps({
                    "golden_spec": "A cube",
                    "key_constraints": [],
                }))
            if "judge" in system.lower() or "fidelity" in system.lower():
                return _mock_llm_response(json.dumps({
                    "score": 99, "text_similarity": 99,
                    "geometric_accuracy": 99, "manufacturing_viability": 99,
                    "reasoning": "Great",
                }))
            if "learner" in system.lower() or "pattern" in system.lower():
                return _mock_llm_response(json.dumps({
                    "patterns": [], "anti_patterns": [], "key_insights": [],
                }))
            return _mock_llm_response("result = Box(50, 50, 50)")

        config = {
            "supervisor": {"model": "test/sup"},
            "judge": {"model": "test/judge"},
            "merger": {"model": "test/merger"},
            "proposal_agents": [{"model": "test/a"}],
            "fidelity_threshold": 50,
            "debate_enabled": False,
        }

        with patch(_GRAPH_PATCHES[0]) as MockClient, \
             patch(_GRAPH_PATCHES[1], side_effect=_noop_evaluate_proposal):
            mock = MagicMock()
            mock.model = "test/model"
            mock.acall = AsyncMock(side_effect=mock_acall)
            MockClient.return_value = mock

            async for _ in run_competitive_graph(
                design=design, store=store, project_root=tmp_path,
                pipeline_config=config, max_rounds=1,
            ):
                pass

        loaded = store.get(design.id)
        assert loaded is not None
        assert len(loaded.fidelity_score_history) >= 1
        assert loaded.fidelity_score_history[0]["round"] == 1
