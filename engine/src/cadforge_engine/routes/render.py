"""Render endpoint — headless STL to PNG rendering."""

from __future__ import annotations

import base64
from pathlib import Path

from fastapi import APIRouter
from pydantic import BaseModel, Field

router = APIRouter()


class RenderRequest(BaseModel):
    """Request to render an STL file to PNG images."""
    stl_path: str = Field(..., description="Path to the STL file to render")
    output_dir: str | None = Field(default=None, description="Output directory for PNGs (defaults to same as STL)")
    include_base64: bool = Field(default=False, description="Include base64-encoded image data in response")
    window_size: list[int] = Field(default=[1024, 768], description="Render resolution [width, height]")


class RenderResult(BaseModel):
    """A single rendered view."""
    view: str
    path: str
    base64_data: str | None = None


class RenderResponse(BaseModel):
    """Response from render endpoint."""
    success: bool
    images: list[RenderResult] = Field(default_factory=list)
    error: str | None = None


@router.post("/tools/render", response_model=RenderResponse)
async def render_endpoint(req: RenderRequest) -> RenderResponse:
    """Render an STL file to PNG images from multiple angles."""
    stl = Path(req.stl_path)
    if not stl.exists():
        return RenderResponse(success=False, error=f"STL file not found: {stl}")

    output_dir = Path(req.output_dir) if req.output_dir else stl.parent
    png_base = output_dir / stl.stem

    try:
        from cadforge_engine.domain.renderer import render_stl_to_png

        ws = (req.window_size[0], req.window_size[1]) if len(req.window_size) >= 2 else (1024, 768)
        paths = render_stl_to_png(stl, png_base, window_size=ws)

        images = []
        for p in paths:
            b64 = None
            if req.include_base64:
                b64 = base64.b64encode(p.read_bytes()).decode("ascii")
            view_name = p.stem.replace(f"{stl.stem}_", "")
            images.append(RenderResult(view=view_name, path=str(p), base64_data=b64))

        return RenderResponse(success=True, images=images)

    except ImportError as e:
        return RenderResponse(success=False, error=f"PyVista not available: {e}")
    except Exception as e:
        return RenderResponse(success=False, error=str(e))
