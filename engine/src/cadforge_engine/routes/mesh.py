"""Mesh analysis and preview endpoints."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter

from cadforge_engine.models.requests import MeshAnalyzeRequest, PreviewRequest
from cadforge_engine.models.responses import MeshAnalysisResponse, PreviewResponse

router = APIRouter(prefix="/tools")


@router.post("/mesh", response_model=MeshAnalysisResponse)
async def analyze_mesh_endpoint(req: MeshAnalyzeRequest) -> MeshAnalysisResponse:
    """Analyze a mesh file for geometry metrics and issues."""
    project_root = Path(req.project_root)
    path = Path(req.path) if Path(req.path).is_absolute() else project_root / req.path

    if not path.exists():
        return MeshAnalysisResponse(success=False, error=f"File not found: {path}")

    try:
        from cadforge_engine.domain.analyzer import analyze_mesh
        analysis = analyze_mesh(path)
        data = analysis.to_dict()
        return MeshAnalysisResponse(success=True, **data)
    except ImportError:
        return MeshAnalysisResponse(success=False, error="trimesh not installed")
    except Exception as e:
        return MeshAnalysisResponse(success=False, error=str(e))


@router.post("/preview", response_model=PreviewResponse)
async def preview_endpoint(req: PreviewRequest) -> PreviewResponse:
    """Launch 3D preview of an STL file."""
    path = Path(req.path)

    if not path.exists():
        return PreviewResponse(success=False, error=f"File not found: {path}")

    try:
        from cadforge_engine.domain.viewer import show_stl
        show_stl(path, color=req.color, background=req.background)
        return PreviewResponse(success=True, message=f"Opened viewer for {path.name}")
    except ImportError:
        return PreviewResponse(success=False, error="pyvista not installed")
    except Exception as e:
        return PreviewResponse(success=False, error=str(e))
