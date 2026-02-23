"""Design lifecycle REST API + SSE streaming for pipeline execution."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from cadforge_engine.models.designs import DesignSpec, DesignStatus, DesignStore
from cadforge_engine.models.requests import CadSubagentProviderConfig

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/designs", tags=["designs"])


# ── Request / Response models ──


class CreateDesignRequest(BaseModel):
    """Create a new design from a plan-mode spec."""
    title: str = Field(..., description="Design title")
    prompt: str = Field(..., description="User's original prompt")
    specification: str = Field(default="", description="Pre-written geometric specification")
    constraints: dict[str, Any] = Field(default_factory=dict)
    project_root: str = Field(..., description="Project root directory path")


class UpdateDesignRequest(BaseModel):
    """Update a design's spec or metadata."""
    title: str | None = None
    specification: str | None = None
    constraints: dict[str, Any] | None = None


class ExecuteDesignRequest(BaseModel):
    """Request to execute/resume a design pipeline."""
    provider_config: CadSubagentProviderConfig | None = Field(
        default=None, description="LLM provider configuration"
    )
    model: str = Field(default="claude-sonnet-4-5-20250929", description="Model to use")
    max_tokens: int = Field(default=8192, description="Max tokens per LLM call")
    max_rounds: int = Field(default=3, ge=1, le=10, description="Max design-code-judge rounds")


# ── Helper ──


def _get_store(project_root: str) -> DesignStore:
    return DesignStore(Path(project_root))


def _sse_event(event_type: str, data: dict[str, Any]) -> str:
    """Format a single SSE event."""
    return f"event: {event_type}\ndata: {json.dumps(data)}\n\n"


# ── Endpoints ──


@router.post("")
async def create_design(req: CreateDesignRequest) -> dict[str, Any]:
    """Create a new design from a plan-mode specification."""
    store = _get_store(req.project_root)
    design = DesignSpec(
        title=req.title,
        prompt=req.prompt,
        specification=req.specification,
        constraints=req.constraints,
    )
    store.save(design)
    return design.model_dump()


@router.get("")
async def list_designs(project_root: str) -> list[dict[str, Any]]:
    """List all designs."""
    store = _get_store(project_root)
    return [d.model_dump() for d in store.list_all()]


@router.get("/{design_id}")
async def get_design(design_id: str, project_root: str) -> dict[str, Any]:
    """Get a design by ID."""
    store = _get_store(project_root)
    design = store.get(design_id)
    if not design:
        raise HTTPException(status_code=404, detail=f"Design {design_id} not found")
    return design.model_dump()


@router.put("/{design_id}")
async def update_design(
    design_id: str, req: UpdateDesignRequest, project_root: str
) -> dict[str, Any]:
    """Update a design's spec or metadata."""
    store = _get_store(project_root)
    design = store.get(design_id)
    if not design:
        raise HTTPException(status_code=404, detail=f"Design {design_id} not found")

    if req.title is not None:
        design.title = req.title
    if req.specification is not None:
        design.specification = req.specification
    if req.constraints is not None:
        design.constraints = req.constraints

    store.save(design)
    return design.model_dump()


@router.post("/{design_id}/approve")
async def approve_design(design_id: str, project_root: str) -> dict[str, Any]:
    """Approve a design, transitioning status to 'approved'."""
    store = _get_store(project_root)
    design = store.get(design_id)
    if not design:
        raise HTTPException(status_code=404, detail=f"Design {design_id} not found")
    if design.status != DesignStatus.DRAFT:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot approve design in '{design.status.value}' status (must be 'draft')",
        )

    design.status = DesignStatus.APPROVED
    store.save(design)
    return design.model_dump()


@router.post("/{design_id}/execute")
async def execute_design(
    design_id: str, req: ExecuteDesignRequest, project_root: str
) -> StreamingResponse:
    """Execute the design pipeline, streaming SSE events."""
    store = _get_store(project_root)
    design = store.get(design_id)
    if not design:
        raise HTTPException(status_code=404, detail=f"Design {design_id} not found")
    if design.status not in (DesignStatus.APPROVED, DesignStatus.FAILED):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot execute design in '{design.status.value}' status (must be 'approved' or 'failed')",
        )

    async def event_generator():
        from cadforge_engine.agent.llm import create_subagent_client
        from cadforge_engine.agent.pipeline import run_design_pipeline_tracked

        if not req.provider_config:
            yield _sse_event("completion", {"text": "No provider_config supplied."})
            yield _sse_event("done", {})
            return

        llm_client = create_subagent_client(
            req.provider_config, model=req.model, max_tokens=req.max_tokens
        )

        try:
            async for event in run_design_pipeline_tracked(
                llm_client=llm_client,
                design=design,
                design_store=store,
                project_root=Path(project_root),
                max_rounds=req.max_rounds,
            ):
                yield _sse_event(event["event"], event["data"])
        except Exception as e:
            logger.exception("Design pipeline error")
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


@router.post("/{design_id}/resume")
async def resume_design(
    design_id: str, req: ExecuteDesignRequest, project_root: str
) -> StreamingResponse:
    """Resume a design from its last iteration, streaming SSE events."""
    store = _get_store(project_root)
    design = store.get(design_id)
    if not design:
        raise HTTPException(status_code=404, detail=f"Design {design_id} not found")
    if not design.iterations:
        raise HTTPException(
            status_code=400, detail="No iterations to resume from. Use /execute instead."
        )

    resume_from = len(design.iterations)

    async def event_generator():
        from cadforge_engine.agent.llm import create_subagent_client
        from cadforge_engine.agent.pipeline import run_design_pipeline_tracked

        if not req.provider_config:
            yield _sse_event("completion", {"text": "No provider_config supplied."})
            yield _sse_event("done", {})
            return

        llm_client = create_subagent_client(
            req.provider_config, model=req.model, max_tokens=req.max_tokens
        )

        try:
            async for event in run_design_pipeline_tracked(
                llm_client=llm_client,
                design=design,
                design_store=store,
                project_root=Path(project_root),
                max_rounds=req.max_rounds,
                resume_from_round=resume_from,
            ):
                yield _sse_event(event["event"], event["data"])
        except Exception as e:
            logger.exception("Design resume error")
            yield _sse_event("completion", {"text": f"Resume error: {e}"})
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


@router.get("/{design_id}/iterations")
async def get_iterations(design_id: str, project_root: str) -> list[dict[str, Any]]:
    """Get iteration history for a design."""
    store = _get_store(project_root)
    design = store.get(design_id)
    if not design:
        raise HTTPException(status_code=404, detail=f"Design {design_id} not found")
    return [it.model_dump() for it in design.iterations]


@router.delete("/{design_id}")
async def delete_design(design_id: str, project_root: str) -> dict[str, str]:
    """Delete a design."""
    store = _get_store(project_root)
    if not store.delete(design_id):
        raise HTTPException(status_code=404, detail=f"Design {design_id} not found")
    return {"status": "deleted", "id": design_id}
