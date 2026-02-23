"""Health check endpoint."""

from __future__ import annotations

from fastapi import APIRouter

from cadforge_engine import __version__
from cadforge_engine.models.responses import HealthResponse

router = APIRouter()


def _detect_capabilities() -> list[str]:
    """Detect which optional dependencies are available."""
    caps = []
    try:
        import cadquery  # noqa: F401
        caps.append("cadquery")
    except Exception:
        pass
    try:
        import build123d  # noqa: F401
        caps.append("build123d")
    except Exception:
        pass
    try:
        import trimesh  # noqa: F401
        caps.append("mesh")
    except Exception:
        pass
    try:
        import lancedb  # noqa: F401
        import sentence_transformers  # noqa: F401
        caps.append("rag")
    except Exception:
        pass
    try:
        import pyvista  # noqa: F401
        caps.append("viewer")
    except Exception:
        pass
    try:
        import anthropic  # noqa: F401
        caps.append("agent")
    except Exception:
        pass
    return caps


@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Return engine health status and available capabilities."""
    return HealthResponse(
        status="ok",
        version=__version__,
        capabilities=_detect_capabilities(),
    )
