"""Competitive multi-agent pipeline orchestrator.

Implements the 9-stage competitive design flow:
  1. Create LiteLLM clients
  2. Load KB context
  3. Supervisor — parse prompt into golden spec + key constraints
  4. Parallel Proposals — asyncio.gather() with all models
  5. Sandbox Evaluation — execute, render, analyze each proposal
  6. Debate/Critique — cross-critique matrix
  7. Fidelity Judge — score each proposal 0-100
  8. Merger/Selector — pick or merge best
  9. Human-in-the-Loop (optional) — pause for approval
  10. Learner — extract patterns
  11. KB Indexer — index into vault

Yields SSE event dicts for real-time UI progress.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
from pathlib import Path
from typing import Any, AsyncGenerator

from cadforge_engine.agent.llm import LiteLLMSubagentClient
from cadforge_engine.agent.pipeline import CODER_TOOLS, _handle_coder_tool
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
# Role-specific system prompts
# ---------------------------------------------------------------------------

SUPERVISOR_PROMPT = """\
You are a CAD design supervisor. Given a user's request for a 3D model,
produce a precise golden specification that multiple CAD programmers will
implement independently.

Your output must be valid JSON with these fields:
{
  "golden_spec": "Detailed geometric specification text...",
  "key_constraints": ["constraint 1", "constraint 2", ...],
  "critical_dimensions": {"name": "value_mm", ...},
  "manufacturing_notes": "Any DFM considerations..."
}

Be extremely specific about dimensions, positions, features, tolerances.
Multiple teams will compete to implement this — ambiguity leads to divergent results.
"""

CODER_PROPOSAL_PROMPT = """\
You are a CAD code generator competing against other models.
Given a golden specification, write the BEST possible build123d or CadQuery code.

Rules:
- Assign the final workpiece to `result`
- CadQuery: use `cq` namespace
- build123d: use `bd` namespace or top-level names (Box, Cylinder, etc.)
- Use `np` for numpy
- Follow the specification exactly — every dimension matters
- Produce clean, well-commented code
- If you receive critique feedback, address each weakness specifically

Available tools: ExecuteCadQuery, SearchVault
"""

CRITIC_PROMPT = """\
You are a CAD design critic. Evaluate another model's proposal against the golden specification.

Output valid JSON:
{
  "strengths": ["strength 1", ...],
  "weaknesses": ["weakness 1", ...],
  "suggested_fixes": ["fix 1", ...],
  "fidelity_concerns": ["concern about spec compliance", ...]
}

Be specific, constructive, and reference exact dimensions from the spec.
"""

FIDELITY_JUDGE_PROMPT = """\
You are a fidelity judge for CAD designs. Score this proposal 0-100 against the golden spec.

Scoring breakdown (these weights are fixed):
- text_similarity (30%): Does the code address all spec requirements?
- geometric_accuracy (40%): Do sandbox metrics match spec dimensions?
- manufacturing_viability (30%): Is it watertight, printable, DFM-clean?

Output valid JSON:
{
  "score": <0-100>,
  "text_similarity": <0-100>,
  "geometric_accuracy": <0-100>,
  "manufacturing_viability": <0-100>,
  "reasoning": "Detailed justification..."
}
"""

MERGER_PROMPT = """\
You are a CAD design merger/selector. Given scored proposals and their critiques,
either select the best one or synthesize a merged solution.

If one proposal clearly wins (score >= threshold), select it.
If multiple proposals have complementary strengths, merge the best parts
into a single improved implementation.

Output valid JSON:
{
  "decision": "select" or "merge",
  "selected_proposal_id": "id" (if select),
  "merged_code": "..." (if merge),
  "reasoning": "Why this decision..."
}
"""

LEARNER_PROMPT = """\
You are a CAD design pattern analyst. Given winning and losing proposals,
extract reusable patterns and anti-patterns.

Output valid JSON:
{
  "patterns": [{"name": "...", "description": "...", "code_snippet": "..."}],
  "anti_patterns": [{"name": "...", "description": "...", "what_went_wrong": "..."}],
  "key_insights": ["insight 1", ...]
}
"""


# ---------------------------------------------------------------------------
# Helper: parse JSON from LLM response text
# ---------------------------------------------------------------------------

def _extract_json(text: str) -> dict[str, Any]:
    """Extract JSON from LLM response, handling markdown code fences."""
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        # Remove first and last lines (fences)
        lines = [l for l in lines if not l.strip().startswith("```")]
        text = "\n".join(lines)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Try to find JSON object in the text
        start = text.find("{")
        end = text.rfind("}") + 1
        if start >= 0 and end > start:
            try:
                return json.loads(text[start:end])
            except json.JSONDecodeError:
                pass
    return {}


def _extract_text(response: dict[str, Any]) -> str:
    """Extract text content from an LLM response."""
    parts = []
    for block in response.get("content", []):
        if block.get("type") == "text":
            parts.append(block["text"])
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Helper: run agentic coder loop
# ---------------------------------------------------------------------------

async def _run_coder_loop(
    client: LiteLLMSubagentClient,
    coder_prompt: str,
    project_root: Path,
    max_turns: int = 10,
) -> tuple[str, str | None, list[str]]:
    """Run an agentic coder loop with tool calls.

    Returns: (code, stl_path, errors)
    """
    messages: list[dict[str, Any]] = [
        {"role": "user", "content": coder_prompt},
    ]
    stl_path: str | None = None
    code = ""
    errors: list[str] = []

    for _ in range(max_turns):
        try:
            response = await client.acall(
                messages=messages,
                system=CODER_PROPOSAL_PROMPT,
                tools=CODER_TOOLS,
            )
        except Exception as e:
            errors.append(f"LLM error: {e}")
            break

        tool_uses = [b for b in response["content"] if b.get("type") == "tool_use"]
        if not tool_uses:
            # Extract any text as reasoning
            text = _extract_text(response)
            if text and not code:
                code = text
            break

        messages.append({"role": "assistant", "content": response["content"]})

        tool_results: list[dict[str, Any]] = []
        for tu in tool_uses:
            result = _handle_coder_tool(tu["name"], tu["input"], project_root)

            if tu["name"] == "ExecuteCadQuery":
                code = tu["input"].get("code", "")

            if result.get("output_path"):
                stl_path = result["output_path"]

            if not result.get("success") and result.get("error"):
                errors.append(result["error"])

            tool_results.append({
                "type": "tool_result",
                "tool_use_id": tu["id"],
                "content": json.dumps(result),
            })

        messages.append({"role": "user", "content": tool_results})

    return code, stl_path, errors


# ---------------------------------------------------------------------------
# Core orchestrator
# ---------------------------------------------------------------------------

async def run_competitive_pipeline(
    design: CompetitiveDesignSpec,
    store: CompetitiveDesignStore,
    project_root: Path,
    pipeline_config: dict[str, Any],
    max_rounds: int = 3,
) -> AsyncGenerator[dict[str, Any], None]:
    """Run the competitive multi-agent pipeline.

    Yields SSE event dicts for real-time progress updates.

    Args:
        design: The competitive design spec (contains prompt, spec, etc.)
        store: Persistence store for crash-safe saving.
        project_root: Project root for sandbox operations.
        pipeline_config: Model role configuration.
        max_rounds: Maximum refinement rounds.
    """
    # ── Stage 1: Create LiteLLM clients ──
    supervisor_model = pipeline_config.get("supervisor", {}).get("model", "minimax/MiniMax-M2.5")
    judge_model = pipeline_config.get("judge", {}).get("model", "zai/glm-5")
    merger_model = pipeline_config.get("merger", {}).get("model", "minimax/MiniMax-M2.5")
    proposal_configs = pipeline_config.get("proposal_agents", [
        {"model": "minimax/MiniMax-M2.5"},
        {"model": "zai/glm-5"},
        {"model": "dashscope/qwen3-coder-next"},
        {"model": "xai/grok-4-1-fast-reasoning"},
    ])
    fidelity_threshold = pipeline_config.get("fidelity_threshold", 95.0)
    debate_enabled = pipeline_config.get("debate_enabled", True)

    supervisor_client = LiteLLMSubagentClient(model=supervisor_model)
    judge_client = LiteLLMSubagentClient(model=judge_model)
    merger_client = LiteLLMSubagentClient(model=merger_model)
    proposal_clients = [LiteLLMSubagentClient(model=pc["model"]) for pc in proposal_configs]

    yield {"event": "competitive_status", "data": {
        "id": design.id, "status": "started",
        "models": [pc["model"] for pc in proposal_configs],
    }}

    # ── Stage 2: Load KB context ──
    kb_context = ""
    try:
        from cadforge_engine.vault.search import search_vault
        results = search_vault(project_root, design.prompt, limit=5)
        if results:
            kb_snippets = [r.get("content", "")[:300] for r in results if isinstance(r, dict)]
            kb_context = "\n---\n".join(kb_snippets)
            design.kb_context = kb_context
    except Exception:
        pass  # KB unavailable is non-fatal

    # ── Stage 3: Supervisor ──
    design.status = CompetitiveDesignStatus.SUPERVISING
    store.save(design)
    yield {"event": "competitive_supervisor", "data": {"status": "running", "model": supervisor_model}}

    supervisor_prompt = f"User request: {design.prompt}"
    if kb_context:
        supervisor_prompt += f"\n\nRelevant knowledge base context:\n{kb_context}"
    if design.specification:
        supervisor_prompt += f"\n\nExisting specification draft:\n{design.specification}"

    try:
        supervisor_response = await supervisor_client.acall(
            messages=[{"role": "user", "content": supervisor_prompt}],
            system=SUPERVISOR_PROMPT,
            tools=[],
        )
        supervisor_text = _extract_text(supervisor_response)
        supervisor_data = _extract_json(supervisor_text)

        golden_spec = supervisor_data.get("golden_spec", supervisor_text)
        key_constraints = supervisor_data.get("key_constraints", [])
        design.specification = golden_spec
        design.constraints = {
            "key_constraints": key_constraints,
            "critical_dimensions": supervisor_data.get("critical_dimensions", {}),
            "manufacturing_notes": supervisor_data.get("manufacturing_notes", ""),
        }
        store.save(design)

        yield {"event": "competitive_supervisor", "data": {
            "status": "completed",
            "golden_spec_length": len(golden_spec),
            "constraint_count": len(key_constraints),
        }}
    except Exception as e:
        logger.exception("Supervisor failed")
        yield {"event": "competitive_status", "data": {"id": design.id, "status": "failed", "error": str(e)}}
        design.status = CompetitiveDesignStatus.FAILED
        store.save(design)
        yield {"event": "completion", "data": {"text": f"Supervisor failed: {e}"}}
        yield {"event": "done", "data": {}}
        return

    # ── Refinement loop ──
    accumulated_feedback: list[str] = []
    previous_stl: str | None = None

    for round_num in range(1, max_rounds + 1):
        yield {"event": "competitive_round", "data": {"round": round_num, "max_rounds": max_rounds}}

        comp_round = CompetitiveRound(round_number=round_num)

        # ── Stage 4: Parallel Proposals ──
        design.status = CompetitiveDesignStatus.PROPOSING
        store.save(design)

        coder_prompt = f"Golden Specification:\n{design.specification}"
        if design.constraints.get("key_constraints"):
            coder_prompt += f"\n\nKey Constraints:\n" + "\n".join(
                f"- {c}" for c in design.constraints["key_constraints"]
            )
        if accumulated_feedback:
            coder_prompt += "\n\nFeedback from previous round(s):\n" + "\n---\n".join(accumulated_feedback)
        if kb_context:
            coder_prompt += f"\n\nRelevant vault patterns:\n{kb_context}"

        # Create proposal stubs
        proposals: list[Proposal] = []
        for pc in proposal_configs:
            p = Proposal(model=pc["model"])
            proposals.append(p)
            yield {"event": "competitive_proposal", "data": {
                "proposal_id": p.id, "model": p.model, "status": "generating",
            }}

        # Run all proposals in parallel
        async def _run_proposal(idx: int) -> tuple[int, str, str | None, list[str]]:
            code, stl, errors = await _run_coder_loop(
                proposal_clients[idx], coder_prompt, project_root,
            )
            return idx, code, stl, errors

        tasks = [_run_proposal(i) for i in range(len(proposal_clients))]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for result in results:
            if isinstance(result, Exception):
                logger.warning("Proposal task failed: %s", result)
                continue
            idx, code, stl_path, errors = result
            p = proposals[idx]
            p.code = code
            p.status = ProposalStatus.COMPLETED if code else ProposalStatus.FAILED
            if errors:
                p.reasoning = "; ".join(errors)
            yield {"event": "competitive_proposal", "data": {
                "proposal_id": p.id, "model": p.model,
                "status": p.status.value, "has_code": bool(code),
                "stl_path": stl_path,
            }}

        # Filter to successful proposals
        valid_proposals = [p for p in proposals if p.status == ProposalStatus.COMPLETED and p.code]
        if not valid_proposals:
            yield {"event": "competitive_status", "data": {"id": design.id, "status": "failed", "reason": "No valid proposals"}}
            design.status = CompetitiveDesignStatus.FAILED
            store.save(design)
            yield {"event": "completion", "data": {"text": "All proposals failed — no valid code produced."}}
            yield {"event": "done", "data": {}}
            return

        # ── Stage 5: Sandbox Evaluation ──
        design.status = CompetitiveDesignStatus.EVALUATING
        store.save(design)

        for p in valid_proposals:
            yield {"event": "competitive_sandbox", "data": {"proposal_id": p.id, "status": "running"}}
            eval_result = _evaluate_proposal(p, project_root, previous_stl)
            p.sandbox_eval = eval_result
            yield {"event": "competitive_sandbox", "data": {
                "proposal_id": p.id, "status": "completed",
                "execution_success": eval_result.execution_success,
                "is_watertight": eval_result.is_watertight,
                "volume_mm3": eval_result.volume_mm3,
                "stl_path": eval_result.stl_path,
                "png_count": len(eval_result.png_paths),
            }}

        # ── Stage 6: Debate/Critique ──
        if debate_enabled and len(valid_proposals) > 1:
            design.status = CompetitiveDesignStatus.DEBATING
            store.save(design)
            yield {"event": "competitive_debate", "data": {"status": "running", "proposal_count": len(valid_proposals)}}

            critique_tasks = []
            for critic_client in proposal_clients:
                for target_p in valid_proposals:
                    if critic_client.model == target_p.model:
                        continue  # Don't critique yourself
                    critique_tasks.append(
                        _run_critique(critic_client, target_p, design.specification, design.constraints)
                    )
            # Also add GLM-5 as dedicated fidelity critic
            critique_tasks.append(
                _run_critique(judge_client, target_p, design.specification, design.constraints)
                for target_p in valid_proposals
            )
            # Flatten the generator
            all_critique_tasks = []
            for item in critique_tasks:
                if asyncio.iscoroutine(item):
                    all_critique_tasks.append(item)
                else:
                    # It's a generator from the comprehension
                    for coro in item:
                        all_critique_tasks.append(coro)

            critique_results = await asyncio.gather(*all_critique_tasks, return_exceptions=True)

            for cr in critique_results:
                if isinstance(cr, Exception):
                    logger.warning("Critique failed: %s", cr)
                    continue
                if isinstance(cr, CritiqueRecord):
                    # Find target proposal and attach
                    for p in valid_proposals:
                        if p.id == cr.target_proposal_id:
                            p.critiques_received.append(cr)
                            break

            yield {"event": "competitive_debate", "data": {
                "status": "completed",
                "total_critiques": sum(len(p.critiques_received) for p in valid_proposals),
            }}

        # ── Stage 7: Fidelity Judge ──
        design.status = CompetitiveDesignStatus.JUDGING
        store.save(design)

        fidelity_tasks = [
            _run_fidelity_judge(judge_client, p, design.specification, design.constraints, fidelity_threshold)
            for p in valid_proposals
        ]
        fidelity_results = await asyncio.gather(*fidelity_tasks, return_exceptions=True)

        for i, fr in enumerate(fidelity_results):
            if isinstance(fr, Exception):
                logger.warning("Fidelity judge failed for proposal: %s", fr)
                continue
            if isinstance(fr, FidelityScore) and i < len(valid_proposals):
                valid_proposals[i].fidelity_score = fr
                yield {"event": "competitive_fidelity", "data": {
                    "proposal_id": fr.proposal_id,
                    "score": fr.score,
                    "passed": fr.passed,
                    "text_similarity": fr.text_similarity,
                    "geometric_accuracy": fr.geometric_accuracy,
                    "manufacturing_viability": fr.manufacturing_viability,
                }}

        # ── Stage 8: Merger/Selector ──
        design.status = CompetitiveDesignStatus.MERGING
        store.save(design)

        passing = [p for p in valid_proposals if p.fidelity_score and p.fidelity_score.passed]
        yield {"event": "competitive_merger", "data": {"status": "running", "passing_count": len(passing)}}

        winner_code: str | None = None
        winner_id: str | None = None

        if len(passing) == 1:
            winner_code = passing[0].code
            winner_id = passing[0].id
            passing[0].status = ProposalStatus.SELECTED
        elif len(passing) > 1:
            # Ask merger to choose or merge
            merger_result = await _run_merger(
                merger_client, passing, design.specification, fidelity_threshold
            )
            if merger_result.get("decision") == "select" and merger_result.get("selected_proposal_id"):
                sel_id = merger_result["selected_proposal_id"]
                for p in passing:
                    if p.id == sel_id:
                        winner_code = p.code
                        winner_id = p.id
                        p.status = ProposalStatus.SELECTED
                        break
                if not winner_code:
                    # Fallback: pick highest scorer
                    best = max(passing, key=lambda p: p.fidelity_score.score if p.fidelity_score else 0)
                    winner_code = best.code
                    winner_id = best.id
                    best.status = ProposalStatus.SELECTED
            elif merger_result.get("merged_code"):
                winner_code = merger_result["merged_code"]
                comp_round.merger_output = winner_code
            else:
                # Fallback: pick highest scorer
                best = max(passing, key=lambda p: p.fidelity_score.score if p.fidelity_score else 0)
                winner_code = best.code
                winner_id = best.id
                best.status = ProposalStatus.SELECTED
        else:
            # No passing proposals — collect feedback for next round
            all_feedback = []
            for p in valid_proposals:
                if p.fidelity_score:
                    all_feedback.append(f"Model {p.model} scored {p.fidelity_score.score}: {p.fidelity_score.reasoning}")
                for c in p.critiques_received:
                    all_feedback.append(f"Critique of {p.model}: weaknesses={c.weaknesses}")
            accumulated_feedback = all_feedback

            yield {"event": "competitive_merger", "data": {
                "status": "no_winner", "round": round_num,
                "reason": "No proposals passed fidelity threshold",
            }}

            # Mark all as rejected
            for p in valid_proposals:
                p.status = ProposalStatus.REJECTED

            comp_round.proposals = proposals
            design.rounds.append(comp_round)
            store.save(design)

            if round_num < max_rounds:
                yield {"event": "competitive_status", "data": {
                    "id": design.id, "status": "retrying",
                    "round": round_num, "reason": "Forced revert — injecting feedback",
                }}
                continue
            else:
                # Max rounds exhausted
                design.status = CompetitiveDesignStatus.FAILED
                store.save(design)
                yield {"event": "competitive_status", "data": {
                    "id": design.id, "status": "failed",
                    "reason": f"No proposal passed threshold after {max_rounds} rounds",
                }}
                yield {"event": "completion", "data": {
                    "text": f"Competitive pipeline failed after {max_rounds} rounds — no proposal met fidelity threshold of {fidelity_threshold}.",
                }}
                yield {"event": "done", "data": {}}
                return

        # We have a winner
        comp_round.proposals = proposals
        comp_round.winner_proposal_id = winner_id
        design.rounds.append(comp_round)
        design.final_code = winner_code

        # Track previous STL for geometric diff
        for p in valid_proposals:
            if p.id == winner_id and p.sandbox_eval and p.sandbox_eval.stl_path:
                previous_stl = p.sandbox_eval.stl_path
                design.final_stl_path = p.sandbox_eval.stl_path

        store.save(design)

        yield {"event": "competitive_merger", "data": {
            "status": "completed",
            "winner_id": winner_id,
            "winner_model": next((p.model for p in valid_proposals if p.id == winner_id), None),
            "has_merged_code": comp_round.merger_output is not None,
        }}

        # ── Stage 9: Human-in-the-Loop (optional) ──
        if pipeline_config.get("human_approval_required", False):
            design.status = CompetitiveDesignStatus.AWAITING_APPROVAL
            store.save(design)
            yield {"event": "competitive_approval_requested", "data": {
                "id": design.id,
                "round": round_num,
                "winner_id": winner_id,
                "final_code": winner_code,
                "stl_path": design.final_stl_path,
            }}
            # Pipeline pauses here — separate endpoint handles approval
            yield {"event": "completion", "data": {
                "text": f"Competitive pipeline paused for human approval (round {round_num}). Design ID: {design.id}",
            }}
            yield {"event": "done", "data": {}}
            return

        # Winner found — proceed to learning
        break

    # ── Stage 10: Learner ──
    design.status = CompetitiveDesignStatus.LEARNING
    store.save(design)
    yield {"event": "competitive_learning", "data": {"status": "running"}}

    try:
        learner_data = await _run_learner(
            LiteLLMSubagentClient(model=supervisor_model),
            design,
        )
        yield {"event": "competitive_learning", "data": {
            "status": "completed",
            "pattern_count": len(learner_data.get("patterns", [])),
            "anti_pattern_count": len(learner_data.get("anti_patterns", [])),
        }}
    except Exception as e:
        logger.warning("Learner failed: %s", e)
        yield {"event": "competitive_learning", "data": {"status": "failed", "error": str(e)}}

    # ── Stage 11: KB Indexer ──
    try:
        from cadforge_engine.vault.learnings import extract_learnings
        from cadforge_engine.vault.indexer import index_chunks

        # Convert competitive design to a DesignSpec-compatible form for learning extraction
        from cadforge_engine.models.designs import DesignSpec, IterationRecord

        compat_design = DesignSpec(
            id=design.id,
            title=design.title,
            prompt=design.prompt,
            specification=design.specification,
        )
        # Add a synthetic approved iteration from the winner
        if design.final_code:
            compat_design.iterations.append(IterationRecord(
                round_number=len(design.rounds),
                code=design.final_code,
                stl_path=design.final_stl_path,
                approved=True,
            ))

        chunks = extract_learnings(compat_design)
        if chunks:
            index_chunks(project_root, chunks)
            design.learnings_indexed = True
            store.save(design)
            yield {"event": "competitive_learning", "data": {
                "indexed": True, "chunk_count": len(chunks),
            }}
    except Exception as e:
        logger.warning("KB indexing failed: %s", e)

    # ── Finalize ──
    design.status = CompetitiveDesignStatus.COMPLETED
    store.save(design)

    summary = f"Competitive pipeline completed after {len(design.rounds)} round(s)."
    if design.final_stl_path:
        summary += f" Output: {design.final_stl_path}"
    summary += f" Winner: {comp_round.winner_proposal_id or 'merged'}"

    yield {"event": "competitive_status", "data": {"id": design.id, "status": "completed"}}
    yield {"event": "completion", "data": {"text": summary, "output_path": design.final_stl_path}}
    yield {"event": "done", "data": {}}


# ---------------------------------------------------------------------------
# Stage helpers
# ---------------------------------------------------------------------------

def _evaluate_proposal(
    proposal: Proposal,
    project_root: Path,
    previous_stl: str | None = None,
) -> SandboxEvaluation:
    """Execute a proposal's code in sandbox and evaluate results."""
    eval_result = SandboxEvaluation(proposal_id=proposal.id)

    if not proposal.code:
        eval_result.execution_error = "No code to execute"
        return eval_result

    try:
        from cadforge_engine.domain.sandbox import execute_cadquery

        output_dir = project_root / "output" / "stl"
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / f"competitive_{proposal.id}.stl"

        result = execute_cadquery(proposal.code, output_path=output_path)
        if not result.success:
            eval_result.execution_error = result.error
            return eval_result

        eval_result.execution_success = True
        if result.has_workpiece:
            eval_result.stl_path = str(output_path)

            # Analyze mesh
            try:
                from cadforge_engine.domain.analyzer import analyze_mesh, run_dfm_check
                analysis = analyze_mesh(output_path)
                eval_result.is_watertight = analysis.is_watertight
                eval_result.volume_mm3 = analysis.volume_mm3
                eval_result.surface_area_mm2 = analysis.surface_area_mm2
                eval_result.bounding_box = analysis.bounding_box
                eval_result.center_of_mass = analysis.center_of_mass

                dfm = run_dfm_check(output_path)
                eval_result.dfm_issues = dfm.issues
            except Exception as e:
                logger.warning("Mesh analysis failed for %s: %s", proposal.id, e)

            # Render PNGs
            try:
                from cadforge_engine.domain.renderer import render_stl_to_png
                png_base = output_path.parent / output_path.stem
                png_paths = render_stl_to_png(output_path, png_base)
                eval_result.png_paths = [str(p) for p in png_paths]
            except Exception as e:
                logger.warning("Rendering failed for %s: %s", proposal.id, e)

            # Geometric diff vs previous
            if previous_stl:
                try:
                    from cadforge_engine.domain.analyzer import compare_meshes
                    diff = compare_meshes(Path(previous_stl), output_path)
                    eval_result.geometric_diff = diff.to_dict()
                except Exception as e:
                    logger.warning("Geometric diff failed: %s", e)

    except Exception as e:
        eval_result.execution_error = str(e)

    return eval_result


async def _run_critique(
    critic_client: LiteLLMSubagentClient,
    target: Proposal,
    specification: str,
    constraints: dict[str, Any],
) -> CritiqueRecord:
    """Run a critique of a target proposal."""
    critique_prompt = (
        f"Golden Specification:\n{specification}\n\n"
        f"Key Constraints:\n{json.dumps(constraints)}\n\n"
        f"Proposal by {target.model}:\n```python\n{target.code}\n```\n\n"
    )
    if target.sandbox_eval:
        critique_prompt += (
            f"Sandbox Results:\n"
            f"  Execution success: {target.sandbox_eval.execution_success}\n"
            f"  Watertight: {target.sandbox_eval.is_watertight}\n"
            f"  Volume: {target.sandbox_eval.volume_mm3} mm³\n"
            f"  DFM issues: {target.sandbox_eval.dfm_issues}\n"
        )

    response = await critic_client.acall(
        messages=[{"role": "user", "content": critique_prompt}],
        system=CRITIC_PROMPT,
        tools=[],
    )
    text = _extract_text(response)
    data = _extract_json(text)

    return CritiqueRecord(
        critic_model=critic_client.model,
        target_proposal_id=target.id,
        strengths=data.get("strengths", []),
        weaknesses=data.get("weaknesses", []),
        suggested_fixes=data.get("suggested_fixes", []),
        fidelity_concerns=data.get("fidelity_concerns", []),
        raw_text=text,
    )


async def _run_fidelity_judge(
    judge_client: LiteLLMSubagentClient,
    proposal: Proposal,
    specification: str,
    constraints: dict[str, Any],
    threshold: float,
) -> FidelityScore:
    """Score a proposal for fidelity to specification."""
    judge_prompt = (
        f"Golden Specification:\n{specification}\n\n"
        f"Key Constraints:\n{json.dumps(constraints)}\n\n"
        f"Proposal Code:\n```python\n{proposal.code}\n```\n\n"
    )
    if proposal.sandbox_eval:
        judge_prompt += (
            f"Sandbox Evaluation:\n"
            f"  Success: {proposal.sandbox_eval.execution_success}\n"
            f"  Watertight: {proposal.sandbox_eval.is_watertight}\n"
            f"  Volume: {proposal.sandbox_eval.volume_mm3} mm³\n"
            f"  Surface area: {proposal.sandbox_eval.surface_area_mm2} mm²\n"
            f"  Bounding box: {proposal.sandbox_eval.bounding_box}\n"
            f"  DFM issues: {proposal.sandbox_eval.dfm_issues}\n"
        )
    if proposal.critiques_received:
        judge_prompt += "\nCritiques received:\n"
        for c in proposal.critiques_received:
            judge_prompt += f"  From {c.critic_model}: weaknesses={c.weaknesses}, fixes={c.suggested_fixes}\n"

    # Include rendered images if available
    messages: list[dict[str, Any]]
    if proposal.sandbox_eval and proposal.sandbox_eval.png_paths:
        content: list[dict[str, Any]] = [{"type": "text", "text": judge_prompt}]
        for png_path in proposal.sandbox_eval.png_paths:
            try:
                image_data = base64.b64encode(Path(png_path).read_bytes()).decode("ascii")
                content.append({
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/png",
                        "data": image_data,
                    },
                })
            except Exception:
                pass
        messages = [{"role": "user", "content": content}]
    else:
        messages = [{"role": "user", "content": judge_prompt}]

    response = await judge_client.acall(
        messages=messages,
        system=FIDELITY_JUDGE_PROMPT,
        tools=[],
    )
    text = _extract_text(response)
    data = _extract_json(text)

    score = float(data.get("score", 0))
    return FidelityScore(
        proposal_id=proposal.id,
        score=score,
        text_similarity=float(data.get("text_similarity", 0)),
        geometric_accuracy=float(data.get("geometric_accuracy", 0)),
        manufacturing_viability=float(data.get("manufacturing_viability", 0)),
        reasoning=data.get("reasoning", text),
        passed=score >= threshold,
    )


async def _run_merger(
    merger_client: LiteLLMSubagentClient,
    passing_proposals: list[Proposal],
    specification: str,
    threshold: float,
) -> dict[str, Any]:
    """Ask the merger to select or merge from passing proposals."""
    merger_prompt = f"Golden Specification:\n{specification}\n\nPassing proposals:\n\n"
    for p in passing_proposals:
        score = p.fidelity_score.score if p.fidelity_score else 0
        merger_prompt += (
            f"--- Proposal {p.id} (model: {p.model}, score: {score}) ---\n"
            f"```python\n{p.code}\n```\n\n"
        )
        if p.critiques_received:
            merger_prompt += f"Critiques: {[c.weaknesses for c in p.critiques_received]}\n\n"

    merger_prompt += f"Fidelity threshold: {threshold}\n"

    response = await merger_client.acall(
        messages=[{"role": "user", "content": merger_prompt}],
        system=MERGER_PROMPT,
        tools=[],
    )
    text = _extract_text(response)
    return _extract_json(text)


async def _run_learner(
    learner_client: LiteLLMSubagentClient,
    design: CompetitiveDesignSpec,
) -> dict[str, Any]:
    """Extract patterns from the competitive results."""
    learner_prompt = f"Design: {design.prompt}\nSpecification: {design.specification[:500]}\n\n"
    for r in design.rounds:
        learner_prompt += f"Round {r.round_number}:\n"
        for p in r.proposals:
            score = p.fidelity_score.score if p.fidelity_score else "N/A"
            learner_prompt += f"  {p.model}: status={p.status.value}, score={score}\n"
            if p.code:
                learner_prompt += f"  Code snippet: {p.code[:200]}...\n"
        if r.winner_proposal_id:
            learner_prompt += f"  Winner: {r.winner_proposal_id}\n"

    response = await learner_client.acall(
        messages=[{"role": "user", "content": learner_prompt}],
        system=LEARNER_PROMPT,
        tools=[],
    )
    text = _extract_text(response)
    return _extract_json(text)
