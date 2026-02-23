"""Pipeline endpoint — design-then-code pipeline with SSE streaming."""

from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from cadforge_engine.models.requests import CadSubagentProviderConfig

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/pipeline")


class DesignPipelineRequest(BaseModel):
    """Request to run the design-then-code pipeline."""
    prompt: str = Field(..., description="User's design request")
    project_root: str = Field(..., description="Project root directory path")
    provider_config: CadSubagentProviderConfig | None = Field(
        default=None, description="LLM provider configuration"
    )
    model: str = Field(default="claude-sonnet-4-5-20250929", description="Model to use")
    max_tokens: int = Field(default=8192, description="Max tokens per LLM call")
    max_rounds: int = Field(default=3, ge=1, le=10, description="Max design-code-judge rounds")


@router.post("/design")
async def design_pipeline_endpoint(req: DesignPipelineRequest) -> StreamingResponse:
    """Run the design pipeline, streaming SSE events."""

    async def event_generator():
        from cadforge_engine.agent.llm import create_subagent_client
        from cadforge_engine.agent.pipeline import run_design_pipeline

        # Create LLM client
        if req.provider_config:
            llm_client = create_subagent_client(
                req.provider_config,
                model=req.model,
                max_tokens=req.max_tokens,
            )
        else:
            yield _sse_event("completion", {"text": "No provider_config supplied."})
            yield _sse_event("done", {})
            return

        try:
            async for event in run_design_pipeline(
                llm_client=llm_client,
                prompt=req.prompt,
                project_root=req.project_root,
                max_rounds=req.max_rounds,
            ):
                yield _sse_event(event["event"], event["data"])
        except Exception as e:
            logger.exception("Pipeline error")
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


def _sse_event(event_type: str, data: dict[str, Any]) -> str:
    """Format a single SSE event."""
    return f"event: {event_type}\ndata: {json.dumps(data)}\n\n"
