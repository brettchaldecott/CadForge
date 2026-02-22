"""LangGraph-based competitive multi-agent pipeline orchestrator.

Replaces the raw asyncio.gather() orchestration in competitive.py with a proper
LangGraph StateGraph providing:
  - Typed state (TypedDict with Annotated reducers)
  - Fan-out/fan-in via Send() for parallel proposals, critiques, and fidelity
  - Human-in-the-loop via interrupt()
  - Checkpointing for crash recovery via MemorySaver
  - SSE event streaming via astream(stream_mode="updates")

Reuses all helper functions and prompts from competitive.py.
"""

from __future__ import annotations

import json
import logging
import operator
from pathlib import Path
from typing import Annotated, Any, AsyncGenerator, TypedDict

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Command, Send, interrupt

from cadforge_engine.agent.competitive import (
    CODER_PROPOSAL_PROMPT,
    CRITIC_PROMPT,
    FIDELITY_JUDGE_PROMPT,
    LEARNER_PROMPT,
    MERGER_PROMPT,
    SUPERVISOR_PROMPT,
    _evaluate_proposal,
    _extract_json,
    _extract_text,
    _run_coder_loop,
    _run_critique,
    _run_fidelity_judge,
    _run_learner,
    _run_merger,
)
from cadforge_engine.agent.llm import LiteLLMSubagentClient
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

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# State schema
# ---------------------------------------------------------------------------

class CompetitivePipelineState(TypedDict, total=False):
    """Typed state for the competitive pipeline graph.

    Uses Annotated[list, add] for append-only accumulation of SSE events
    and critiques. Other fields are overwritten per-node.
    """
    # Inputs (set once)
    design_id: str
    prompt: str
    specification: str
    project_root: str
    pipeline_config: dict
    max_rounds: int
    fidelity_threshold: float
    debate_enabled: bool

    # SSE events to emit (append-only via reducer)
    sse_events: Annotated[list[dict], operator.add]

    # Supervisor outputs
    golden_spec: str
    key_constraints: list[str]
    constraints: dict
    kb_context: str

    # Per-round state
    current_round: int
    proposals: list[dict]
    _proposal_results: Annotated[list[dict], operator.add]  # fan-in from workers
    sandbox_evals: list[dict]
    critiques: Annotated[list[dict], operator.add]
    _fidelity_results: Annotated[list[dict], operator.add]  # fan-in from workers
    fidelity_scores: list[dict]
    accumulated_feedback: list[str]
    previous_stl: str

    # Merger output
    winner_code: str
    winner_id: str
    winner_model: str

    # History accumulators (append-only via reducer)
    version_history: Annotated[list[dict], operator.add]
    fidelity_score_history: Annotated[list[dict], operator.add]

    # Learnings
    learner_data: dict

    # Terminal
    final_status: str
    final_message: str

    # Worker-specific (set by Send())
    _worker_index: int
    _worker_model: str
    _critic_model: str
    _target: dict
    _target_proposal: dict


# ---------------------------------------------------------------------------
# Node functions
# ---------------------------------------------------------------------------

def init_clients(state: CompetitivePipelineState) -> dict:
    """Create LiteLLM clients (no-op node; clients are created per-call)."""
    config = state["pipeline_config"]
    models = [pc["model"] for pc in config.get("proposal_agents", [])]
    return {
        "sse_events": [{"event": "competitive_status", "data": {
            "id": state["design_id"], "status": "started", "models": models,
        }}],
    }


def load_kb(state: CompetitivePipelineState) -> dict:
    """Search vault for relevant patterns/learnings."""
    kb_context = ""
    try:
        from cadforge_engine.vault.search import search_vault
        results = search_vault(Path(state["project_root"]), state["prompt"], limit=5)
        if results:
            snippets = [r.get("content", "")[:300] for r in results if isinstance(r, dict)]
            kb_context = "\n---\n".join(snippets)
    except Exception:
        pass  # KB unavailable is non-fatal
    return {"kb_context": kb_context}


async def supervisor(state: CompetitivePipelineState) -> dict:
    """Parse prompt into golden spec + key constraints."""
    config = state["pipeline_config"]
    supervisor_model = config.get("supervisor", {}).get("model", "minimax/MiniMax-M2.5")
    client = LiteLLMSubagentClient(model=supervisor_model)

    supervisor_prompt = f"User request: {state['prompt']}"
    kb_context = state.get("kb_context", "")
    if kb_context:
        supervisor_prompt += f"\n\nRelevant knowledge base context:\n{kb_context}"
    spec = state.get("specification", "")
    if spec:
        supervisor_prompt += f"\n\nExisting specification draft:\n{spec}"

    response = await client.acall(
        messages=[{"role": "user", "content": supervisor_prompt}],
        system=SUPERVISOR_PROMPT,
        tools=[],
    )

    text = _extract_text(response)
    data = _extract_json(text)

    golden_spec = data.get("golden_spec", text)
    key_constraints = data.get("key_constraints", [])
    constraints = {
        "key_constraints": key_constraints,
        "critical_dimensions": data.get("critical_dimensions", {}),
        "manufacturing_notes": data.get("manufacturing_notes", ""),
    }

    return {
        "golden_spec": golden_spec,
        "key_constraints": key_constraints,
        "constraints": constraints,
        "specification": golden_spec,
        "sse_events": [
            {"event": "competitive_supervisor", "data": {"status": "running", "model": supervisor_model}},
            {"event": "competitive_supervisor", "data": {
                "status": "completed",
                "golden_spec_length": len(golden_spec),
                "constraint_count": len(key_constraints),
            }},
        ],
    }


def prepare_round(state: CompetitivePipelineState) -> dict:
    """Increment round counter and prepare coder prompt context."""
    current_round = state.get("current_round", 0) + 1
    return {
        "current_round": current_round,
        "proposals": [],
        "sandbox_evals": [],
        "fidelity_scores": [],
        "sse_events": [{"event": "competitive_round", "data": {
            "round": current_round, "max_rounds": state["max_rounds"],
        }}],
    }


def fan_out_proposals(state: CompetitivePipelineState) -> list[Send]:
    """Fan-out: dispatch one proposal_worker per agent model."""
    configs = state["pipeline_config"].get("proposal_agents", [])
    return [
        Send("proposal_worker", {**state, "_worker_index": i, "_worker_model": cfg["model"]})
        for i, cfg in enumerate(configs)
    ]


async def proposal_worker(state: CompetitivePipelineState) -> dict:
    """Execute a single proposal via the agentic coder loop."""
    idx = state["_worker_index"]
    model = state["_worker_model"]
    client = LiteLLMSubagentClient(model=model)

    # Build coder prompt
    coder_prompt = f"Golden Specification:\n{state.get('golden_spec', state.get('specification', ''))}"
    key_constraints = state.get("key_constraints", [])
    if key_constraints:
        coder_prompt += "\n\nKey Constraints:\n" + "\n".join(f"- {c}" for c in key_constraints)
    feedback = state.get("accumulated_feedback", [])
    if feedback:
        coder_prompt += "\n\nFeedback from previous round(s):\n" + "\n---\n".join(feedback)
    kb = state.get("kb_context", "")
    if kb:
        coder_prompt += f"\n\nRelevant vault patterns:\n{kb}"

    proposal = Proposal(model=model)

    try:
        code, stl_path, errors = await _run_coder_loop(
            client, coder_prompt, Path(state["project_root"]),
        )
        proposal.code = code
        proposal.status = ProposalStatus.COMPLETED if code else ProposalStatus.FAILED
        if errors:
            proposal.reasoning = "; ".join(errors)
    except Exception as e:
        proposal.status = ProposalStatus.FAILED
        proposal.reasoning = str(e)
        stl_path = None

    return {
        "_proposal_results": [proposal.model_dump()],
        "sse_events": [{"event": "competitive_proposal", "data": {
            "proposal_id": proposal.id, "model": model,
            "status": proposal.status.value, "has_code": bool(proposal.code),
            "stl_path": stl_path,
        }}],
    }


def collect_proposals(state: CompetitivePipelineState) -> dict:
    """Fan-in: gather all proposal results and filter valid ones."""
    proposals = state.get("_proposal_results", [])
    valid = [p for p in proposals if p.get("status") == ProposalStatus.COMPLETED.value and p.get("code")]

    if not valid:
        return {
            "final_status": "failed",
            "final_message": "All proposals failed — no valid code produced.",
            "sse_events": [{"event": "competitive_status", "data": {
                "id": state["design_id"], "status": "failed", "reason": "No valid proposals",
            }}],
        }

    return {"proposals": proposals}


def sandbox_evaluator(state: CompetitivePipelineState) -> dict:
    """Sequentially sandbox-execute, render, and analyze each valid proposal."""
    proposals = state.get("proposals", [])
    previous_stl = state.get("previous_stl", "")
    events: list[dict] = []
    updated_proposals: list[dict] = []

    for p_dict in proposals:
        if p_dict.get("status") != ProposalStatus.COMPLETED.value or not p_dict.get("code"):
            updated_proposals.append(p_dict)
            continue

        proposal = Proposal(**p_dict)
        events.append({"event": "competitive_sandbox", "data": {
            "proposal_id": proposal.id, "status": "running",
        }})

        eval_result = _evaluate_proposal(
            proposal, Path(state["project_root"]),
            previous_stl if previous_stl else None,
        )
        proposal.sandbox_eval = eval_result

        events.append({"event": "competitive_sandbox", "data": {
            "proposal_id": proposal.id, "status": "completed",
            "execution_success": eval_result.execution_success,
            "is_watertight": eval_result.is_watertight,
            "volume_mm3": eval_result.volume_mm3,
            "stl_path": eval_result.stl_path,
            "png_count": len(eval_result.png_paths),
        }})

        updated_proposals.append(proposal.model_dump())

    return {"proposals": updated_proposals, "sse_events": events}


def route_debate(state: CompetitivePipelineState) -> str:
    """Conditional: debate_enabled AND >1 valid proposal?"""
    if not state.get("debate_enabled", True):
        return "fan_out_fidelity"

    valid = [p for p in state.get("proposals", [])
             if p.get("status") == ProposalStatus.COMPLETED.value and p.get("code")]
    if len(valid) <= 1:
        return "fan_out_fidelity"

    return "fan_out_critiques"


def fan_out_critiques(state: CompetitivePipelineState) -> list[Send]:
    """Fan-out: NxN critique tasks (excluding self-critique)."""
    config = state["pipeline_config"]
    models = [pc["model"] for pc in config.get("proposal_agents", [])]
    valid = [p for p in state.get("proposals", [])
             if p.get("status") == ProposalStatus.COMPLETED.value and p.get("code")]

    sends = []
    for critic_model in models:
        for target in valid:
            if critic_model != target.get("model"):
                sends.append(Send("critique_worker", {
                    **state, "_critic_model": critic_model, "_target": target,
                }))

    # Also include the judge as a dedicated critic
    judge_model = config.get("judge", {}).get("model", "zai/glm-5")
    for target in valid:
        sends.append(Send("critique_worker", {
            **state, "_critic_model": judge_model, "_target": target,
        }))

    if not sends:
        return [Send("collect_critiques", state)]

    return sends


async def critique_worker(state: CompetitivePipelineState) -> dict:
    """Execute a single critique of a target proposal."""
    critic_model = state["_critic_model"]
    target_dict = state["_target"]
    target = Proposal(**target_dict)
    client = LiteLLMSubagentClient(model=critic_model)

    try:
        critique = await _run_critique(
            client, target,
            state.get("specification", state.get("golden_spec", "")),
            state.get("constraints", {}),
        )
        return {
            "critiques": [critique.model_dump()],
            "sse_events": [{"event": "competitive_debate", "data": {
                "critic": critic_model, "target": target.id, "status": "completed",
            }}],
        }
    except Exception as e:
        logger.warning("Critique failed: %s", e)
        return {"critiques": [], "sse_events": []}


def collect_critiques(state: CompetitivePipelineState) -> dict:
    """Fan-in: attach critiques to their target proposals."""
    critiques = state.get("critiques", [])
    proposals = list(state.get("proposals", []))

    # Attach critiques to target proposals
    for p_dict in proposals:
        pid = p_dict.get("id", "")
        matching = [c for c in critiques if c.get("target_proposal_id") == pid]
        existing = p_dict.get("critiques_received", [])
        p_dict["critiques_received"] = existing + matching

    total_critiques = sum(len(p.get("critiques_received", [])) for p in proposals)

    return {
        "proposals": proposals,
        "sse_events": [{"event": "competitive_debate", "data": {
            "status": "completed", "total_critiques": total_critiques,
        }}],
    }


def fan_out_fidelity(state: CompetitivePipelineState) -> list[Send]:
    """Fan-out: one fidelity scoring task per valid proposal."""
    valid = [p for p in state.get("proposals", [])
             if p.get("status") == ProposalStatus.COMPLETED.value and p.get("code")]
    return [
        Send("fidelity_worker", {**state, "_target_proposal": p})
        for p in valid
    ]


async def fidelity_worker(state: CompetitivePipelineState) -> dict:
    """Score a single proposal for fidelity to specification."""
    config = state["pipeline_config"]
    judge_model = config.get("judge", {}).get("model", "zai/glm-5")
    client = LiteLLMSubagentClient(model=judge_model)

    target_dict = state["_target_proposal"]
    proposal = Proposal(**target_dict)

    try:
        fs = await _run_fidelity_judge(
            client, proposal,
            state.get("specification", state.get("golden_spec", "")),
            state.get("constraints", {}),
            state.get("fidelity_threshold", 95.0),
        )
        return {
            "_fidelity_results": [fs.model_dump()],
            "sse_events": [{"event": "competitive_fidelity", "data": {
                "proposal_id": fs.proposal_id,
                "score": fs.score,
                "passed": fs.passed,
                "text_similarity": fs.text_similarity,
                "geometric_accuracy": fs.geometric_accuracy,
                "manufacturing_viability": fs.manufacturing_viability,
            }}],
        }
    except Exception as e:
        logger.warning("Fidelity judge failed: %s", e)
        return {"_fidelity_results": [], "sse_events": []}


def collect_fidelity(state: CompetitivePipelineState) -> dict:
    """Fan-in: attach fidelity scores to proposals and snapshot history."""
    scores = state.get("_fidelity_results", [])
    proposals = list(state.get("proposals", []))

    for p_dict in proposals:
        pid = p_dict.get("id", "")
        matching = [s for s in scores if s.get("proposal_id") == pid]
        if matching:
            p_dict["fidelity_score"] = matching[0]

    return {
        "proposals": proposals,
        "fidelity_score_history": [{
            "round": state.get("current_round", 1),
            "scores": scores,
        }],
    }


async def merger_selector(state: CompetitivePipelineState) -> dict:
    """Pick winner, merge, or trigger revert for next round."""
    config = state["pipeline_config"]
    merger_model = config.get("merger", {}).get("model", "minimax/MiniMax-M2.5")
    threshold = state.get("fidelity_threshold", 95.0)
    proposals = state.get("proposals", [])

    # Find passing proposals
    passing = []
    for p_dict in proposals:
        fs = p_dict.get("fidelity_score")
        if fs and fs.get("passed"):
            passing.append(p_dict)

    events: list[dict] = [{"event": "competitive_merger", "data": {
        "status": "running", "passing_count": len(passing),
    }}]

    winner_code = ""
    winner_id = ""
    winner_model = ""

    if len(passing) == 1:
        passing[0]["status"] = ProposalStatus.SELECTED.value
        winner_code = passing[0].get("code", "")
        winner_id = passing[0].get("id", "")
        winner_model = passing[0].get("model", "")
    elif len(passing) > 1:
        # Ask merger to choose or merge
        passing_proposals = [Proposal(**p) for p in passing]
        merger_client = LiteLLMSubagentClient(model=merger_model)
        merger_result = await _run_merger(
            merger_client, passing_proposals,
            state.get("specification", state.get("golden_spec", "")),
            threshold,
        )

        if merger_result.get("decision") == "select" and merger_result.get("selected_proposal_id"):
            sel_id = merger_result["selected_proposal_id"]
            for p_dict in passing:
                if p_dict.get("id") == sel_id:
                    p_dict["status"] = ProposalStatus.SELECTED.value
                    winner_code = p_dict.get("code", "")
                    winner_id = p_dict.get("id", "")
                    winner_model = p_dict.get("model", "")
                    break
            if not winner_code:
                # Fallback: highest scorer
                best = max(passing, key=lambda p: (p.get("fidelity_score") or {}).get("score", 0))
                best["status"] = ProposalStatus.SELECTED.value
                winner_code = best.get("code", "")
                winner_id = best.get("id", "")
                winner_model = best.get("model", "")
        elif merger_result.get("merged_code"):
            winner_code = merger_result["merged_code"]
            winner_id = "merged"
            winner_model = "merged"
        else:
            # Fallback: highest scorer
            best = max(passing, key=lambda p: (p.get("fidelity_score") or {}).get("score", 0))
            best["status"] = ProposalStatus.SELECTED.value
            winner_code = best.get("code", "")
            winner_id = best.get("id", "")
            winner_model = best.get("model", "")
    else:
        # No passing proposals — collect feedback for next round
        all_feedback = []
        for p_dict in proposals:
            fs = p_dict.get("fidelity_score")
            if fs:
                all_feedback.append(
                    f"Model {p_dict.get('model')} scored {fs.get('score')}: {fs.get('reasoning', '')}"
                )
            for c in p_dict.get("critiques_received", []):
                all_feedback.append(
                    f"Critique of {p_dict.get('model')}: weaknesses={c.get('weaknesses', [])}"
                )

        # Mark all as rejected
        for p_dict in proposals:
            if p_dict.get("status") == ProposalStatus.COMPLETED.value:
                p_dict["status"] = ProposalStatus.REJECTED.value

        events.append({"event": "competitive_merger", "data": {
            "status": "no_winner",
            "round": state.get("current_round", 1),
            "reason": "No proposals passed fidelity threshold",
        }})

        current_round = state.get("current_round", 1)
        return {
            "proposals": proposals,
            "accumulated_feedback": all_feedback,
            "winner_code": "",
            "winner_id": "",
            "winner_model": "",
            "version_history": [{
                "round": current_round,
                "proposal_count": len(proposals),
                "passing_count": 0,
                "winner_id": "",
                "scores": [
                    {
                        "id": p.get("id", ""),
                        "model": p.get("model", ""),
                        "score": (p.get("fidelity_score") or {}).get("score", 0),
                    }
                    for p in proposals
                ],
            }],
            "sse_events": events,
        }

    # Winner found
    events.append({"event": "competitive_merger", "data": {
        "status": "completed",
        "winner_id": winner_id,
        "winner_model": winner_model,
        "has_merged_code": winner_id == "merged",
    }})

    # Track STL path from winner
    prev_stl = state.get("previous_stl", "")
    for p_dict in proposals:
        if p_dict.get("id") == winner_id:
            se = p_dict.get("sandbox_eval")
            if se and se.get("stl_path"):
                prev_stl = se["stl_path"]

    current_round = state.get("current_round", 1)
    return {
        "proposals": proposals,
        "winner_code": winner_code,
        "winner_id": winner_id,
        "winner_model": winner_model,
        "previous_stl": prev_stl,
        "version_history": [{
            "round": current_round,
            "proposal_count": len(proposals),
            "passing_count": len(passing),
            "winner_id": winner_id,
            "scores": [
                {
                    "id": p.get("id", ""),
                    "model": p.get("model", ""),
                    "score": (p.get("fidelity_score") or {}).get("score", 0),
                }
                for p in proposals
            ],
        }],
        "sse_events": events,
    }


def route_after_merger(state: CompetitivePipelineState) -> str:
    """Conditional routing after merger: winner, retry, or fail."""
    winner_code = state.get("winner_code", "")
    current_round = state.get("current_round", 1)
    max_rounds = state.get("max_rounds", 3)

    if winner_code:
        # Winner found — check if human approval needed
        config = state.get("pipeline_config", {})
        if config.get("human_approval_required", False):
            return "human_approval"
        return "learner"

    # No winner
    if current_round < max_rounds:
        return "prepare_round"

    # Rounds exhausted
    return "finalize_failed"


def human_approval(state: CompetitivePipelineState) -> dict:
    """Pause graph for human-in-the-loop approval via interrupt()."""
    # Find STL path
    stl_path = state.get("previous_stl", "")

    decision = interrupt({
        "design_id": state["design_id"],
        "winner_id": state.get("winner_id", ""),
        "final_code": state.get("winner_code", ""),
        "stl_path": stl_path,
    })

    approved = decision.get("approved", False) if isinstance(decision, dict) else False
    feedback = decision.get("feedback", "") if isinstance(decision, dict) else ""

    if approved:
        return {
            "final_status": "completed",
            "sse_events": [{"event": "competitive_approval_response", "data": {
                "approved": True, "feedback": feedback,
            }}],
        }
    else:
        return {
            "final_status": "failed",
            "final_message": f"Human rejected design. Feedback: {feedback}",
            "sse_events": [{"event": "competitive_approval_response", "data": {
                "approved": False, "feedback": feedback,
            }}],
        }


async def learner(state: CompetitivePipelineState) -> dict:
    """Extract patterns from winning/losing proposals."""
    config = state["pipeline_config"]
    supervisor_model = config.get("supervisor", {}).get("model", "minimax/MiniMax-M2.5")
    client = LiteLLMSubagentClient(model=supervisor_model)

    events: list[dict] = [{"event": "competitive_learning", "data": {"status": "running"}}]
    learner_data: dict = {}

    try:
        # Build a minimal CompetitiveDesignSpec for the learner
        design = CompetitiveDesignSpec(
            id=state["design_id"],
            prompt=state["prompt"],
            specification=state.get("specification", state.get("golden_spec", "")),
        )
        # Add a round with the proposals
        proposals = [Proposal(**p) for p in state.get("proposals", [])]
        comp_round = CompetitiveRound(
            round_number=state.get("current_round", 1),
            proposals=proposals,
            winner_proposal_id=state.get("winner_id", ""),
        )
        design.rounds.append(comp_round)
        design.final_code = state.get("winner_code", "")

        learner_data = await _run_learner(client, design)
        events.append({"event": "competitive_learning", "data": {
            "status": "completed",
            "pattern_count": len(learner_data.get("patterns", [])),
            "anti_pattern_count": len(learner_data.get("anti_patterns", [])),
        }})
    except Exception as e:
        logger.warning("Learner failed: %s", e)
        events.append({"event": "competitive_learning", "data": {
            "status": "failed", "error": str(e),
        }})

    return {"learner_data": learner_data, "sse_events": events}


def kb_indexer(state: CompetitivePipelineState) -> dict:
    """Index learnings into LanceDB vault."""
    events: list[dict] = []

    try:
        from cadforge_engine.vault.learnings import extract_learnings
        from cadforge_engine.vault.indexer import index_chunks
        from cadforge_engine.models.designs import DesignSpec, IterationRecord

        compat_design = DesignSpec(
            id=state["design_id"],
            title=state.get("prompt", "")[:80],
            prompt=state["prompt"],
            specification=state.get("specification", state.get("golden_spec", "")),
        )
        winner_code = state.get("winner_code", "")
        if winner_code:
            compat_design.iterations.append(IterationRecord(
                round_number=state.get("current_round", 1),
                code=winner_code,
                stl_path=state.get("previous_stl"),
                approved=True,
            ))

        chunks = extract_learnings(compat_design)
        if chunks:
            index_chunks(Path(state["project_root"]), chunks)
            events.append({"event": "competitive_learning", "data": {
                "indexed": True, "chunk_count": len(chunks),
            }})
    except Exception as e:
        logger.warning("KB indexing failed: %s", e)

    return {"sse_events": events}


def finalize(state: CompetitivePipelineState) -> dict:
    """Set final status and build success summary."""
    winner_id = state.get("winner_id", "")
    stl_path = state.get("previous_stl", "")
    current_round = state.get("current_round", 1)
    status = state.get("final_status", "completed")

    summary = f"Competitive pipeline completed after {current_round} round(s)."
    if stl_path:
        summary += f" Output: {stl_path}"
    summary += f" Winner: {winner_id or 'merged'}"

    return {
        "final_status": status,
        "final_message": summary,
        "sse_events": [
            {"event": "competitive_status", "data": {
                "id": state["design_id"], "status": status,
                "version_history": state.get("version_history", []),
                "fidelity_score_history": state.get("fidelity_score_history", []),
            }},
            {"event": "completion", "data": {
                "text": summary, "output_path": stl_path,
            }},
            {"event": "done", "data": {}},
        ],
    }


def finalize_failed(state: CompetitivePipelineState) -> dict:
    """Set final status for exhausted rounds."""
    max_rounds = state.get("max_rounds", 3)
    threshold = state.get("fidelity_threshold", 95.0)
    msg = (
        f"Competitive pipeline failed after {max_rounds} rounds "
        f"— no proposal met fidelity threshold of {threshold}."
    )

    return {
        "final_status": "failed",
        "final_message": msg,
        "sse_events": [
            {"event": "competitive_status", "data": {
                "id": state["design_id"], "status": "failed",
                "reason": f"No proposal passed threshold after {max_rounds} rounds",
                "version_history": state.get("version_history", []),
                "fidelity_score_history": state.get("fidelity_score_history", []),
            }},
            {"event": "completion", "data": {"text": msg}},
            {"event": "done", "data": {}},
        ],
    }


# ---------------------------------------------------------------------------
# Graph builder
# ---------------------------------------------------------------------------

def build_competitive_graph(checkpointer: Any | None = None) -> CompiledStateGraph:
    """Build and compile the competitive pipeline graph.

    Args:
        checkpointer: LangGraph checkpointer for interrupt/resume and crash
            recovery. Defaults to MemorySaver if None.

    Returns:
        Compiled StateGraph ready for astream().
    """
    builder = StateGraph(CompetitivePipelineState)

    # Add nodes
    builder.add_node("init_clients", init_clients)
    builder.add_node("load_kb", load_kb)
    builder.add_node("supervisor", supervisor)
    builder.add_node("prepare_round", prepare_round)
    builder.add_node("proposal_worker", proposal_worker)
    builder.add_node("collect_proposals", collect_proposals)
    builder.add_node("sandbox_evaluator", sandbox_evaluator)
    builder.add_node("critique_worker", critique_worker)
    builder.add_node("collect_critiques", collect_critiques)
    builder.add_node("fidelity_worker", fidelity_worker)
    builder.add_node("collect_fidelity", collect_fidelity)
    builder.add_node("merger_selector", merger_selector)
    builder.add_node("human_approval", human_approval)
    builder.add_node("learner", learner)
    builder.add_node("kb_indexer", kb_indexer)
    builder.add_node("finalize", finalize)
    builder.add_node("finalize_failed", finalize_failed)

    # Edges
    builder.add_edge(START, "init_clients")
    builder.add_edge("init_clients", "load_kb")
    builder.add_edge("load_kb", "supervisor")
    builder.add_edge("supervisor", "prepare_round")

    # Fan-out proposals
    builder.add_conditional_edges("prepare_round", fan_out_proposals)
    builder.add_edge("proposal_worker", "collect_proposals")

    # After collecting proposals — check if any valid
    builder.add_conditional_edges("collect_proposals", lambda state: (
        "finalize_failed" if state.get("final_status") == "failed"
        else "sandbox_evaluator"
    ))

    builder.add_edge("sandbox_evaluator", "route_debate_node")

    # Route debate is a conditional edge — we use a passthrough node
    builder.add_node("route_debate_node", lambda state: {})
    builder.add_conditional_edges("route_debate_node", route_debate)

    # Fan-out critiques
    builder.add_conditional_edges("fan_out_critiques", fan_out_critiques)
    builder.add_node("fan_out_critiques", lambda state: {
        "sse_events": [{"event": "competitive_debate", "data": {
            "status": "running",
            "proposal_count": len([
                p for p in state.get("proposals", [])
                if p.get("status") == ProposalStatus.COMPLETED.value
            ]),
        }}],
    })
    builder.add_edge("critique_worker", "collect_critiques")
    builder.add_edge("collect_critiques", "fan_out_fidelity_node")

    # Fan-out fidelity
    builder.add_node("fan_out_fidelity_node", lambda state: {})
    builder.add_conditional_edges("fan_out_fidelity_node", fan_out_fidelity)
    # Direct path from route_debate skipping critiques
    builder.add_node("fan_out_fidelity", lambda state: {})
    builder.add_conditional_edges("fan_out_fidelity", fan_out_fidelity)
    builder.add_edge("fidelity_worker", "collect_fidelity")

    builder.add_edge("collect_fidelity", "merger_selector")

    # After merger
    builder.add_conditional_edges("merger_selector", route_after_merger)

    # Human approval → learner or finalize
    builder.add_conditional_edges("human_approval", lambda state: (
        "learner" if state.get("final_status") == "completed"
        else "finalize"
    ))

    builder.add_edge("learner", "kb_indexer")
    builder.add_edge("kb_indexer", "finalize")
    builder.add_edge("finalize", END)
    builder.add_edge("finalize_failed", END)

    if checkpointer is None:
        checkpointer = MemorySaver()

    return builder.compile(checkpointer=checkpointer)


# ---------------------------------------------------------------------------
# Public streaming API
# ---------------------------------------------------------------------------

async def run_competitive_graph(
    design: CompetitiveDesignSpec,
    store: CompetitiveDesignStore,
    project_root: Path,
    pipeline_config: dict[str, Any],
    max_rounds: int = 3,
    checkpointer: Any | None = None,
) -> AsyncGenerator[dict[str, Any], None]:
    """Stream SSE events from the competitive pipeline graph.

    This is the primary public API. It builds the graph, initializes state,
    streams updates via astream(stream_mode="updates"), and persists design
    state to the store after each node.

    Args:
        design: The competitive design spec.
        store: Persistence store for crash-safe saving.
        project_root: Project root for sandbox operations.
        pipeline_config: Model role configuration dict.
        max_rounds: Maximum refinement rounds.
        checkpointer: Optional LangGraph checkpointer (defaults to MemorySaver).

    Yields:
        SSE event dicts with "event" and "data" keys.
    """
    graph = build_competitive_graph(checkpointer=checkpointer)

    initial_state: CompetitivePipelineState = {
        "design_id": design.id,
        "prompt": design.prompt,
        "specification": design.specification,
        "project_root": str(project_root),
        "pipeline_config": pipeline_config,
        "max_rounds": max_rounds,
        "fidelity_threshold": pipeline_config.get("fidelity_threshold", 95.0),
        "debate_enabled": pipeline_config.get("debate_enabled", True),
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

    config = {"configurable": {"thread_id": design.id}}

    async for chunk in graph.astream(initial_state, config, stream_mode="updates"):
        for node_name, node_output in chunk.items():
            if node_output is None:
                continue
            if not isinstance(node_output, dict):
                continue
            events = node_output.get("sse_events", [])
            for ev in events:
                yield ev

            # Update design state from graph outputs for persistence
            if "final_status" in node_output and node_output["final_status"]:
                status_map = {
                    "completed": CompetitiveDesignStatus.COMPLETED,
                    "failed": CompetitiveDesignStatus.FAILED,
                    "awaiting_approval": CompetitiveDesignStatus.AWAITING_APPROVAL,
                }
                new_status = status_map.get(node_output["final_status"])
                if new_status:
                    design.status = new_status

            if "golden_spec" in node_output:
                design.specification = node_output["golden_spec"]

            if "constraints" in node_output:
                design.constraints = node_output["constraints"]

            if "winner_code" in node_output and node_output["winner_code"]:
                design.final_code = node_output["winner_code"]

            if "previous_stl" in node_output and node_output["previous_stl"]:
                design.final_stl_path = node_output["previous_stl"]

            if "version_history" in node_output:
                design.version_history.extend(node_output["version_history"])

            if "fidelity_score_history" in node_output:
                design.fidelity_score_history.extend(node_output["fidelity_score_history"])

            store.save(design)
