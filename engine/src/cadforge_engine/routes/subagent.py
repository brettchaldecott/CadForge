"""CAD subagent SSE endpoint.

Accepts a POST to /subagent/cad with a prompt and streams SSE events
as the Python-side CAD agent iterates on CadQuery code.
"""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from cadforge_engine.agent.cad_agent import run_cad_subagent
from cadforge_engine.agent.llm import create_subagent_client
from cadforge_engine.models.requests import CadSubagentRequest

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/subagent")


@router.post("/cad")
async def cad_subagent_endpoint(req: CadSubagentRequest) -> StreamingResponse:
    """Run the CAD subagent and stream SSE events."""
    try:
        # Prefer provider_config; fall back to legacy auth dict
        if req.provider_config is not None:
            llm_client = create_subagent_client(
                provider_config=req.provider_config,
                model=req.model,
                max_tokens=req.max_tokens,
            )
        elif req.auth:
            # Legacy path: treat auth as Anthropic credentials
            llm_client = create_subagent_client(
                provider_config=req.auth,
                model=req.model,
                max_tokens=req.max_tokens,
            )
        else:
            async def error_stream():
                yield _format_sse("completion", {"text": "Error: No auth credentials or provider config provided"})
                yield _format_sse("done", {})

            return StreamingResponse(
                error_stream(),
                media_type="text/event-stream",
                headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
            )
    except Exception as e:
        logger.exception("Failed to create LLM client")

        async def client_error_stream():
            yield _format_sse("completion", {"text": f"Error creating LLM client: {e}"})
            yield _format_sse("done", {})

        return StreamingResponse(
            client_error_stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    async def event_stream():
        try:
            async for event in run_cad_subagent(
                llm_client=llm_client,
                prompt=req.prompt,
                context=req.context,
                project_root=req.project_root,
            ):
                yield _format_sse(event["event"], event["data"])
        except Exception as e:
            logger.exception("CAD subagent error")
            yield _format_sse("completion", {"text": f"Subagent error: {e}"})
            yield _format_sse("done", {})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _format_sse(event: str, data: dict) -> str:
    """Format a single SSE event."""
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"
