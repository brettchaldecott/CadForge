"""CAD subagent SSE endpoint — placeholder for Phase 4."""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/subagent")

# The CAD subagent SSE endpoint will be implemented in Phase 4.
# It will accept a POST to /subagent/cad with a prompt and stream
# SSE events (status, text_delta, tool_use_start, tool_result, completion, done)
# as the Python-side CAD agent iterates on CadQuery code.
