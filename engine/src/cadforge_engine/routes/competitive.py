"""Competitive multi-agent pipeline REST API + SSE streaming."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from cadforge_engine.models.competitive import (
    CompetitiveDesignSpec,
    CompetitiveDesignStatus,
    CompetitiveDesignStore,
)
from cadforge_engine.models.requests import CompetitivePipelineConfig

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/competitive", tags=["competitive"])


# ── Request models ──


class CreateCompetitiveRequest(BaseModel):
    """Create and start a competitive pipeline."""
    prompt: str = Field(..., description="User's design request")
    project_root: str = Field(..., description="Project root directory")
    specification: str = Field(default="", description="Optional pre-written spec")
    constraints: dict[str, Any] = Field(default_factory=dict)
    pipeline_config: CompetitivePipelineConfig = Field(default_factory=CompetitivePipelineConfig)
    max_rounds: int = Field(default=3, ge=1, le=10)


class ApprovalRequest(BaseModel):
    """Human approval response."""
    approved: bool
    feedback: str = ""


# ── Helpers ──


def _get_store(project_root: str) -> CompetitiveDesignStore:
    return CompetitiveDesignStore(Path(project_root))


def _sse_event(event_type: str, data: dict[str, Any]) -> str:
    """Format a single SSE event."""
    return f"event: {event_type}\ndata: {json.dumps(data)}\n\n"


# ── Endpoints ──


@router.post("")
async def create_competitive(req: CreateCompetitiveRequest) -> StreamingResponse:
    """Create a new competitive design and start the pipeline (SSE stream)."""
    store = _get_store(req.project_root)
    design = CompetitiveDesignSpec(
        title=req.prompt[:80],
        prompt=req.prompt,
        specification=req.specification,
        constraints=req.constraints,
        pipeline_config=req.pipeline_config.model_dump(),
    )
    store.save(design)

    async def event_generator():
        from cadforge_engine.agent.competitive import run_competitive_pipeline

        try:
            async for event in run_competitive_pipeline(
                design=design,
                store=store,
                project_root=Path(req.project_root),
                pipeline_config=req.pipeline_config.model_dump(),
                max_rounds=req.max_rounds,
            ):
                yield _sse_event(event["event"], event["data"])
        except Exception as e:
            logger.exception("Competitive pipeline error")
            yield _sse_event("completion", {"text": f"Pipeline error: {e}"})
            yield _sse_event("done", {})

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/{design_id}/execute")
async def execute_competitive(
    design_id: str, req: CreateCompetitiveRequest
) -> StreamingResponse:
    """Execute/resume a competitive pipeline for an existing design (SSE stream)."""
    store = _get_store(req.project_root)
    design = store.get(design_id)
    if not design:
        raise HTTPException(status_code=404, detail=f"Competitive design {design_id} not found")

    config = req.pipeline_config.model_dump() if req.pipeline_config else design.pipeline_config

    async def event_generator():
        from cadforge_engine.agent.competitive import run_competitive_pipeline

        try:
            async for event in run_competitive_pipeline(
                design=design,
                store=store,
                project_root=Path(req.project_root),
                pipeline_config=config,
                max_rounds=req.max_rounds,
            ):
                yield _sse_event(event["event"], event["data"])
        except Exception as e:
            logger.exception("Competitive pipeline error")
            yield _sse_event("completion", {"text": f"Pipeline error: {e}"})
            yield _sse_event("done", {})

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/{design_id}/approve")
async def approve_competitive(
    design_id: str, req: ApprovalRequest, project_root: str
) -> dict[str, Any]:
    """Submit human approval/rejection for a competitive design."""
    store = _get_store(project_root)
    design = store.get(design_id)
    if not design:
        raise HTTPException(status_code=404, detail=f"Competitive design {design_id} not found")
    if design.status != CompetitiveDesignStatus.AWAITING_APPROVAL:
        raise HTTPException(
            status_code=400,
            detail=f"Design is not awaiting approval (status: {design.status.value})",
        )

    if req.approved:
        design.status = CompetitiveDesignStatus.COMPLETED
    else:
        design.status = CompetitiveDesignStatus.FAILED
        if req.feedback:
            design.constraints["rejection_feedback"] = req.feedback

    store.save(design)
    return design.model_dump()


@router.get("/{design_id}")
async def get_competitive(design_id: str, project_root: str) -> dict[str, Any]:
    """Get a competitive design by ID."""
    store = _get_store(project_root)
    design = store.get(design_id)
    if not design:
        raise HTTPException(status_code=404, detail=f"Competitive design {design_id} not found")
    return design.model_dump()


@router.get("/{design_id}/proposals")
async def get_proposals(design_id: str, project_root: str) -> list[dict[str, Any]]:
    """Get all proposals across all rounds for a competitive design."""
    store = _get_store(project_root)
    design = store.get(design_id)
    if not design:
        raise HTTPException(status_code=404, detail=f"Competitive design {design_id} not found")

    all_proposals = []
    for r in design.rounds:
        for p in r.proposals:
            all_proposals.append({
                "round": r.round_number,
                **p.model_dump(),
            })
    return all_proposals
