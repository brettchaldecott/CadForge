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
from cadforge_engine.agent.llm import SubagentLLMClient
from cadforge_engine.models.requests import CadSubagentRequest

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/subagent")


@router.post("/cad")
async def cad_subagent_endpoint(req: CadSubagentRequest) -> StreamingResponse:
    """Run the CAD subagent and stream SSE events."""
    # Extract auth from forwarded credentials
    api_key = req.auth.get("api_key")
    auth_token = req.auth.get("auth_token")

    if not api_key and not auth_token:
        async def error_stream():
            yield _format_sse("completion", {"text": "Error: No auth credentials provided"})
            yield _format_sse("done", {})

        return StreamingResponse(
            error_stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    llm_client = SubagentLLMClient(
        api_key=api_key,
        auth_token=auth_token,
        model=req.model,
        max_tokens=req.max_tokens,
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
