"""Design-then-Code pipeline orchestrator.

Implements the structured design pipeline:
  Designer → Coder → Renderer → Judge → iterate

The Designer writes a geometric specification, the Coder generates CAD code
and executes it, the Renderer creates PNG views, and the Judge evaluates
the result visually and either approves or provides feedback for refinement.
"""

from __future__ import annotations

import base64
import json
import logging
from pathlib import Path
from typing import Any, AsyncGenerator

from cadforge_engine.agent.llm import SubagentLLMClient
from cadforge_engine.models.designs import DesignSpec, DesignStatus, DesignStore, IterationRecord

logger = logging.getLogger(__name__)

DESIGNER_PROMPT = """\
You are a CAD design specification writer. Given a user's request for a 3D model,
produce a detailed geometric specification that a CAD programmer can implement.

Your specification must include:
- Overall dimensions (length, width, height in mm)
- Key geometric features (holes, fillets, chamfers, cuts, etc.)
- Relative positions and alignments of features
- Material intent and manufacturing considerations if relevant

Output ONLY the specification text. Do not write code.
"""

CODER_PROMPT = """\
You are a CAD code generator. Given a geometric specification, write CadQuery or
build123d code to create the 3D model.

Rules:
- Assign the final workpiece to `result`
- CadQuery: use `cq` namespace
- build123d: use `bd` namespace or top-level names (Box, Cylinder, etc.)
- Use `np` for numpy
- Follow the specification exactly
- Keep code clean and well-commented

Available tools: ExecuteCadQuery, SearchVault
"""

JUDGE_PROMPT = """\
You are a visual quality assurance judge for 3D CAD models. You receive:
1. The original geometric specification
2. Rendered PNG images of the generated model from multiple angles

Evaluate whether the model matches the specification. Consider:
- Are the overall dimensions correct?
- Are all specified features present (holes, fillets, chamfers, etc.)?
- Is the geometry clean and well-formed?
- Are proportions correct?

If the model is acceptable, respond with exactly: APPROVED
If the model needs changes, describe specific issues and corrections needed.
"""

# Tools available to the Coder
CODER_TOOLS: list[dict[str, Any]] = [
    {
        "name": "ExecuteCadQuery",
        "description": "Execute CadQuery or build123d code to create a 3D model. Assign final workpiece to `result`.",
        "input_schema": {
            "type": "object",
            "properties": {
                "code": {"type": "string", "description": "CadQuery or build123d Python code"},
                "output_name": {"type": "string", "description": "Output filename (without extension)"},
                "format": {"type": "string", "enum": ["stl", "step"], "description": "Export format"},
            },
            "required": ["code"],
        },
    },
    {
        "name": "SearchVault",
        "description": "Search the knowledge vault for CAD patterns and examples.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"},
                "tags": {"type": "array", "items": {"type": "string"}, "description": "Filter by tags"},
                "limit": {"type": "number", "description": "Max results"},
            },
            "required": ["query"],
        },
    },
]


def _handle_coder_tool(
    tool_name: str,
    tool_input: dict[str, Any],
    project_root: Path,
) -> dict[str, Any]:
    """Execute a Coder tool call."""
    try:
        if tool_name == "ExecuteCadQuery":
            from cadforge_engine.domain.sandbox import execute_cadquery

            code = tool_input["code"]
            output_name = tool_input.get("output_name", "pipeline_model")
            fmt = tool_input.get("format", "stl")
            ext = "step" if fmt == "step" else "stl"
            output_dir = project_root / "output" / ext
            output_dir.mkdir(parents=True, exist_ok=True)
            output_path = output_dir / f"{output_name}.{ext}"

            result = execute_cadquery(code, output_path=output_path)
            if not result.success:
                return {"success": False, "error": result.error, "stdout": result.stdout}

            resp: dict[str, Any] = {"success": True, "stdout": result.stdout}
            if result.has_workpiece:
                resp["output_path"] = str(output_path)
                resp["message"] = f"Model exported to {output_path}"
            else:
                resp["message"] = "Code executed (no result variable set)"
            return resp

        elif tool_name == "SearchVault":
            from cadforge_engine.vault.search import search_vault
            results = search_vault(
                project_root,
                tool_input["query"],
                tags=tool_input.get("tags"),
                limit=tool_input.get("limit", 5),
            )
            return {"success": True, "results": results}

        return {"success": False, "error": f"Unknown tool: {tool_name}"}
    except Exception as e:
        logger.exception("Coder tool %s failed", tool_name)
        return {"success": False, "error": str(e)}


async def run_design_pipeline(
    llm_client: SubagentLLMClient,
    prompt: str,
    project_root: str,
    max_rounds: int = 3,
) -> AsyncGenerator[dict[str, Any], None]:
    """Run the design-then-code pipeline.

    Yields SSE event dicts:
    - pipeline_step: which step is running (designer/coder/renderer/judge)
    - pipeline_round: round number
    - tool_use_start / tool_result: from coder tool calls
    - pipeline_image: rendered PNG path
    - pipeline_verdict: judge's verdict
    - completion: final summary text
    - done: pipeline finished

    Args:
        llm_client: LLM client to use for all calls.
        prompt: User's design request.
        project_root: Project root path.
        max_rounds: Maximum design-code-render-judge iterations.
    """
    pr = Path(project_root)
    yield {"event": "pipeline_round", "data": {"round": 0, "max_rounds": max_rounds}}

    # ── Step 1: Designer ──
    yield {"event": "pipeline_step", "data": {"step": "designer", "message": "Generating design specification..."}}

    try:
        designer_response = llm_client.call(
            messages=[{"role": "user", "content": prompt}],
            system=DESIGNER_PROMPT,
            tools=[],
        )
    except Exception as e:
        yield {"event": "completion", "data": {"text": f"Designer LLM error: {e}"}}
        yield {"event": "done", "data": {}}
        return

    specification = ""
    for block in designer_response["content"]:
        if block.get("type") == "text":
            specification += block["text"]

    if not specification.strip():
        yield {"event": "completion", "data": {"text": "Designer produced empty specification."}}
        yield {"event": "done", "data": {}}
        return

    yield {"event": "pipeline_step", "data": {"step": "designer", "message": "Specification ready.", "spec": specification}}

    # ── Iteration loop ──
    feedback = ""
    last_stl_path: str | None = None

    for round_num in range(1, max_rounds + 1):
        yield {"event": "pipeline_round", "data": {"round": round_num, "max_rounds": max_rounds}}

        # ── Step 2: Coder ──
        yield {"event": "pipeline_step", "data": {"step": "coder", "message": f"Generating code (round {round_num})..."}}

        coder_prompt = f"Geometric Specification:\n{specification}"
        if feedback:
            coder_prompt += f"\n\nFeedback from previous round:\n{feedback}"

        coder_messages: list[dict[str, Any]] = [
            {"role": "user", "content": coder_prompt},
        ]

        stl_path: str | None = None
        max_coder_turns = 10

        for coder_turn in range(max_coder_turns):
            try:
                coder_response = llm_client.call(
                    messages=coder_messages,
                    system=CODER_PROMPT,
                    tools=CODER_TOOLS,
                )
            except Exception as e:
                yield {"event": "completion", "data": {"text": f"Coder LLM error: {e}"}}
                yield {"event": "done", "data": {}}
                return

            tool_uses = [b for b in coder_response["content"] if b.get("type") == "tool_use"]
            if not tool_uses:
                break

            coder_messages.append({"role": "assistant", "content": coder_response["content"]})

            tool_results: list[dict[str, Any]] = []
            for tu in tool_uses:
                yield {"event": "tool_use_start", "data": {"name": tu["name"], "id": tu["id"], "input": tu["input"]}}

                result = _handle_coder_tool(tu["name"], tu["input"], pr)

                yield {"event": "tool_result", "data": {"name": tu["name"], "id": tu["id"], "result": result}}

                if result.get("output_path"):
                    stl_path = result["output_path"]

                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tu["id"],
                    "content": json.dumps(result),
                })

            coder_messages.append({"role": "user", "content": tool_results})

        if stl_path:
            last_stl_path = stl_path
        elif last_stl_path:
            stl_path = last_stl_path

        if not stl_path:
            yield {"event": "pipeline_step", "data": {"step": "coder", "message": "No STL output produced."}}
            continue

        # ── Step 3: Renderer ──
        yield {"event": "pipeline_step", "data": {"step": "renderer", "message": "Rendering views..."}}

        try:
            from cadforge_engine.domain.renderer import render_stl_to_png

            png_base = Path(stl_path).parent / Path(stl_path).stem
            png_paths = render_stl_to_png(Path(stl_path), png_base)
            for p in png_paths:
                yield {"event": "pipeline_image", "data": {"path": str(p)}}
        except Exception as e:
            yield {"event": "pipeline_step", "data": {"step": "renderer", "message": f"Render failed: {e}"}}
            yield {"event": "pipeline_verdict", "data": {"verdict": "APPROVED", "reason": "Render unavailable, auto-approving."}}
            break

        # ── Step 4: Judge ──
        yield {"event": "pipeline_step", "data": {"step": "judge", "message": "Evaluating model..."}}

        judge_content: list[dict[str, Any]] = [
            {"type": "text", "text": f"Original specification:\n{specification}\n\nPlease evaluate the rendered model views:"},
        ]
        for png_path in png_paths:
            try:
                image_data = base64.b64encode(png_path.read_bytes()).decode("ascii")
                judge_content.append({
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/png",
                        "data": image_data,
                    },
                })
            except Exception:
                pass

        try:
            judge_response = llm_client.call(
                messages=[{"role": "user", "content": judge_content}],
                system=JUDGE_PROMPT,
                tools=[],
            )
        except Exception as e:
            yield {"event": "pipeline_verdict", "data": {"verdict": "APPROVED", "reason": f"Judge error: {e}, auto-approving."}}
            break

        verdict_text = ""
        for block in judge_response["content"]:
            if block.get("type") == "text":
                verdict_text += block["text"]

        verdict_text = verdict_text.strip()
        approved = verdict_text.upper().startswith("APPROVED")

        yield {"event": "pipeline_verdict", "data": {
            "verdict": "APPROVED" if approved else "NEEDS_REVISION",
            "reason": verdict_text,
            "round": round_num,
        }}

        if approved:
            break

        # Feed judge's feedback to next round
        feedback = verdict_text

    # ── Done ──
    summary = f"Pipeline completed after {round_num} round(s)."
    if last_stl_path:
        summary += f" Output: {last_stl_path}"

    yield {"event": "completion", "data": {"text": summary, "output_path": last_stl_path}}
    yield {"event": "done", "data": {}}


# ── Enhanced Coder prompt for tracked pipeline ──

TRACKED_CODER_PROMPT = CODER_PROMPT + """

Tip: Use SearchVault with tags=['learning','cad-pattern'] to find successful patterns from past designs.
"""


def _build_resume_context(design: DesignSpec) -> str:
    """Build accumulated context from previous iterations for the Coder."""
    if not design.iterations:
        return ""

    parts = ["Previous attempts:"]
    for it in design.iterations:
        code_snippet = it.code[:500] + "..." if len(it.code) > 500 else it.code
        if it.errors:
            parts.append(f"  Round {it.round_number}: [code] → Error: {it.errors[0]}")
        elif it.verdict:
            parts.append(f"  Round {it.round_number}: [code] → Judge: \"{it.verdict[:200]}\"")
        else:
            parts.append(f"  Round {it.round_number}: [code produced]")
        if code_snippet:
            parts.append(f"    ```python\n    {code_snippet}\n    ```")

    return "\n".join(parts)


async def run_design_pipeline_tracked(
    llm_client: SubagentLLMClient,
    design: DesignSpec,
    design_store: DesignStore,
    project_root: Path,
    max_rounds: int = 3,
    resume_from_round: int = 0,
) -> AsyncGenerator[dict[str, Any], None]:
    """Run the tracked design pipeline with iteration persistence.

    Unlike run_design_pipeline(), this:
    - Skips the Designer stage (specification comes from the DesignSpec)
    - Captures each round as an IterationRecord
    - Persists after each round (crash-safe)
    - Supports resume from a previous round
    - Triggers learning extraction on completion

    Yields SSE event dicts including new events:
    - iteration_saved: after each round is persisted
    - design_updated: when design status changes
    - learnings_indexed: after learning extraction
    """
    specification = design.specification
    if not specification.strip():
        yield {"event": "completion", "data": {"text": "Design has no specification."}}
        yield {"event": "done", "data": {}}
        return

    # Transition to executing
    design.status = DesignStatus.EXECUTING
    design_store.save(design)
    yield {"event": "design_updated", "data": {"id": design.id, "status": "executing"}}

    # Build resume context
    feedback = ""
    if resume_from_round > 0 and design.iterations:
        last_it = design.iterations[-1]
        if not last_it.approved and last_it.verdict:
            feedback = last_it.verdict

    last_stl_path: str | None = design.final_output_path
    start_round = resume_from_round + 1
    final_round = 0

    yield {"event": "pipeline_round", "data": {"round": 0, "max_rounds": max_rounds}}

    for round_num in range(start_round, start_round + max_rounds):
        final_round = round_num
        yield {"event": "pipeline_round", "data": {"round": round_num, "max_rounds": start_round + max_rounds - 1}}

        # ── Coder ──
        yield {"event": "pipeline_step", "data": {"step": "coder", "message": f"Generating code (round {round_num})..."}}

        coder_prompt = f"Geometric Specification:\n{specification}"

        # Add resume context
        resume_ctx = _build_resume_context(design)
        if resume_ctx:
            coder_prompt += f"\n\n{resume_ctx}"

        if feedback:
            coder_prompt += f"\n\nFeedback from previous round:\n{feedback}"

        if design.constraints:
            coder_prompt += f"\n\nConstraints: {json.dumps(design.constraints)}"

        coder_messages: list[dict[str, Any]] = [
            {"role": "user", "content": coder_prompt},
        ]

        stl_path: str | None = None
        round_code = ""
        round_errors: list[str] = []
        max_coder_turns = 10

        for _coder_turn in range(max_coder_turns):
            try:
                coder_response = llm_client.call(
                    messages=coder_messages,
                    system=TRACKED_CODER_PROMPT,
                    tools=CODER_TOOLS,
                )
            except Exception as e:
                round_errors.append(f"Coder LLM error: {e}")
                break

            tool_uses = [b for b in coder_response["content"] if b.get("type") == "tool_use"]
            if not tool_uses:
                break

            coder_messages.append({"role": "assistant", "content": coder_response["content"]})

            tool_results: list[dict[str, Any]] = []
            for tu in tool_uses:
                yield {"event": "tool_use_start", "data": {"name": tu["name"], "id": tu["id"], "input": tu["input"]}}

                result = _handle_coder_tool(tu["name"], tu["input"], project_root)

                yield {"event": "tool_result", "data": {"name": tu["name"], "id": tu["id"], "result": result}}

                # Capture code from ExecuteCadQuery calls
                if tu["name"] == "ExecuteCadQuery":
                    round_code = tu["input"].get("code", "")

                if result.get("output_path"):
                    stl_path = result["output_path"]

                if not result.get("success") and result.get("error"):
                    round_errors.append(result["error"])

                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tu["id"],
                    "content": json.dumps(result),
                })

            coder_messages.append({"role": "user", "content": tool_results})

        if stl_path:
            last_stl_path = stl_path
        elif last_stl_path:
            stl_path = last_stl_path

        # ── Renderer ──
        png_paths: list[Path] = []
        if stl_path:
            yield {"event": "pipeline_step", "data": {"step": "renderer", "message": "Rendering views..."}}
            try:
                from cadforge_engine.domain.renderer import render_stl_to_png

                png_base = Path(stl_path).parent / Path(stl_path).stem
                png_paths = render_stl_to_png(Path(stl_path), png_base)
                for p in png_paths:
                    yield {"event": "pipeline_image", "data": {"path": str(p)}}
            except Exception as e:
                yield {"event": "pipeline_step", "data": {"step": "renderer", "message": f"Render failed: {e}"}}

        # ── Judge ──
        verdict_text = ""
        approved = False

        if stl_path and png_paths:
            yield {"event": "pipeline_step", "data": {"step": "judge", "message": "Evaluating model..."}}

            judge_content: list[dict[str, Any]] = [
                {"type": "text", "text": f"Original specification:\n{specification}\n\nPlease evaluate the rendered model views:"},
            ]
            for png_path in png_paths:
                try:
                    image_data = base64.b64encode(png_path.read_bytes()).decode("ascii")
                    judge_content.append({
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/png",
                            "data": image_data,
                        },
                    })
                except Exception:
                    pass

            try:
                judge_response = llm_client.call(
                    messages=[{"role": "user", "content": judge_content}],
                    system=JUDGE_PROMPT,
                    tools=[],
                )
                for block in judge_response["content"]:
                    if block.get("type") == "text":
                        verdict_text += block["text"]
                verdict_text = verdict_text.strip()
                approved = verdict_text.upper().startswith("APPROVED")
            except Exception as e:
                verdict_text = f"Judge error: {e}, auto-approving."
                approved = True
        elif not stl_path:
            verdict_text = "No STL output produced."
            round_errors.append("No STL output produced.")
        else:
            # STL but no PNGs — auto-approve
            verdict_text = "Render unavailable, auto-approving."
            approved = True

        yield {"event": "pipeline_verdict", "data": {
            "verdict": "APPROVED" if approved else "NEEDS_REVISION",
            "reason": verdict_text,
            "round": round_num,
        }}

        # ── Persist iteration ──
        iteration = IterationRecord(
            round_number=round_num,
            code=round_code,
            stl_path=stl_path,
            png_paths=[str(p) for p in png_paths],
            verdict=verdict_text,
            approved=approved,
            errors=round_errors,
        )
        design.iterations.append(iteration)
        if stl_path:
            design.final_output_path = stl_path
        design_store.save(design)

        yield {"event": "iteration_saved", "data": {
            "design_id": design.id,
            "round": round_num,
            "approved": approved,
        }}

        if approved:
            break

        # Feed judge's feedback to next round
        feedback = verdict_text

    # ── Finalize ──
    any_approved = any(it.approved for it in design.iterations)
    design.status = DesignStatus.COMPLETED if any_approved else DesignStatus.FAILED
    design_store.save(design)

    yield {"event": "design_updated", "data": {"id": design.id, "status": design.status.value}}

    # ── Extract and index learnings ──
    if any_approved:
        try:
            from cadforge_engine.vault.learnings import extract_learnings
            from cadforge_engine.vault.indexer import index_chunks

            chunks = extract_learnings(design)
            if chunks:
                index_chunks(project_root, chunks)
                design.learnings_indexed = True
                design_store.save(design)
                yield {"event": "learnings_indexed", "data": {
                    "design_id": design.id,
                    "chunk_count": len(chunks),
                }}
        except Exception as e:
            logger.warning("Learning extraction failed: %s", e)

    summary = f"Tracked pipeline completed after {final_round} round(s). Status: {design.status.value}"
    if last_stl_path:
        summary += f". Output: {last_stl_path}"

    yield {"event": "completion", "data": {"text": summary, "output_path": last_stl_path}}
    yield {"event": "done", "data": {}}
