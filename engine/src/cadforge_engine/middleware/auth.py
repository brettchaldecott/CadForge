"""Optional API key authentication middleware.

Skipped when running locally (no API key configured).
Enable by setting CADFORGE_API_KEY environment variable or passing --api-key.
"""

from __future__ import annotations

import os

from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response


class APIKeyMiddleware(BaseHTTPMiddleware):
    """Check X-API-Key header against configured key."""

    def __init__(self, app, api_key: str | None = None) -> None:  # type: ignore[override]
        super().__init__(app)
        self._api_key = api_key or os.environ.get("CADFORGE_API_KEY")

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        # Skip auth if no key configured
        if not self._api_key:
            return await call_next(request)

        # Allow health checks without auth
        if request.url.path == "/health":
            return await call_next(request)

        # Check header
        provided = request.headers.get("X-API-Key")
        if provided != self._api_key:
            raise HTTPException(status_code=401, detail="Invalid or missing API key")

        return await call_next(request)
