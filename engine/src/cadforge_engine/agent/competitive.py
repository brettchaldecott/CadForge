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

import base64
import json
import logging
from pathlib import Path
from typing import Any, AsyncGenerator

from cadforge_engine.agent.llm import LiteLLMSubagentClient
from cadforge_engine.agent.pipeline import CODER_TOOLS, _handle_coder_tool
from cadforge_engine.models.competitive import (
    CompetitiveDesignSpec,
    CompetitiveDesignStore,
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
You are a fidelity judge for CAD designs. Provide a SUBJECTIVE evaluation 0-100
that will be blended with an algorithmic score. Focus on qualitative aspects that
algorithms cannot assess: code intent matching, feature completeness, engineering
judgment, and overall design quality.

Scoring breakdown (your subjective weights):
- text_similarity (30%): Does the code address all spec requirements in spirit?
- geometric_accuracy (40%): Does the design look correct for its intended purpose?
- manufacturing_viability (30%): Engineering judgment on printability/robustness.

Your score will be blended 40% with a 60% algorithmic score that checks exact
dimensions, volume sanity, and DFM metrics. Focus on what algorithms miss.

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

    .. deprecated::
        Use :func:`cadforge_engine.agent.competitive_graph.run_competitive_graph`
        instead, which provides LangGraph-based orchestration with checkpointing,
        fan-out/fan-in via Send(), and human-in-the-loop via interrupt().

    Yields SSE event dicts for real-time progress updates.

    Args:
        design: The competitive design spec (contains prompt, spec, etc.)
        store: Persistence store for crash-safe saving.
        project_root: Project root for sandbox operations.
        pipeline_config: Model role configuration.
        max_rounds: Maximum refinement rounds.
    """
    import warnings
    warnings.warn(
        "run_competitive_pipeline is deprecated, use run_competitive_graph "
        "from cadforge_engine.agent.competitive_graph instead",
        DeprecationWarning,
        stacklevel=2,
    )
    from cadforge_engine.agent.competitive_graph import run_competitive_graph
    async for event in run_competitive_graph(
        design=design, store=store, project_root=project_root,
        pipeline_config=pipeline_config, max_rounds=max_rounds,
    ):
        yield event
    return


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
                eval_result.dfm_report_data = dfm.to_dict()
            except Exception as e:
                logger.warning("Mesh analysis failed for %s: %s", proposal.id, e)

            # FEA stub
            try:
                from cadforge_engine.domain.analyzer import run_fea_stub
                fea = run_fea_stub(output_path)
                eval_result.fea_risk_level = fea.risk_level
                eval_result.fea_risk_score = fea.risk_score
                eval_result.fea_notes = fea.notes
            except Exception as e:
                logger.warning("FEA stub failed for %s: %s", proposal.id, e)

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
    """Score a proposal for fidelity to specification (hybrid algo+LLM)."""
    from cadforge_engine.domain.analyzer import compute_algorithmic_fidelity

    # --- Compute algorithmic score ---
    algo_result = compute_algorithmic_fidelity(
        sandbox_eval=proposal.sandbox_eval.model_dump() if proposal.sandbox_eval else {},
        critical_dimensions=constraints.get("critical_dimensions", {}),
        dfm_report=proposal.sandbox_eval.dfm_report_data if proposal.sandbox_eval else None,
    )

    # --- Build LLM prompt ---
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
        if proposal.sandbox_eval.fea_risk_level:
            judge_prompt += (
                f"  FEA risk: {proposal.sandbox_eval.fea_risk_level} "
                f"(score: {proposal.sandbox_eval.fea_risk_score})\n"
                f"  FEA notes: {proposal.sandbox_eval.fea_notes}\n"
            )

    # Inject algorithmic analysis so the LLM can see it
    judge_prompt += (
        f"\nAlgorithmic analysis:\n"
        f"  Dimension match: {algo_result.dimension_match_score:.1f}/100\n"
        f"  Volume sanity: {algo_result.volume_sanity_score:.1f}/100\n"
        f"  DFM score: {algo_result.dfm_score:.1f}/100\n"
        f"  Overall algorithmic: {algo_result.overall_score:.1f}/100\n"
    )
    if algo_result.notes:
        judge_prompt += f"  Notes: {algo_result.notes}\n"

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

    llm_score = float(data.get("score", 0))
    algo_score = algo_result.overall_score

    # Blend: 60% algorithmic + 40% LLM
    blended_score = algo_score * 0.60 + llm_score * 0.40

    return FidelityScore(
        proposal_id=proposal.id,
        score=blended_score,
        text_similarity=float(data.get("text_similarity", 0)),
        geometric_accuracy=float(data.get("geometric_accuracy", 0)),
        manufacturing_viability=float(data.get("manufacturing_viability", 0)),
        algorithmic_score=algo_score,
        llm_score=llm_score,
        algorithmic_details=algo_result.to_dict(),
        reasoning=data.get("reasoning", text),
        passed=blended_score >= threshold,
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
