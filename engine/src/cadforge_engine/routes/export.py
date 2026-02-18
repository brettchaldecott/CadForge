"""Model export endpoint."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter

from cadforge_engine.models.requests import ExportRequest
from cadforge_engine.models.responses import ExportResponse

router = APIRouter(prefix="/tools")


@router.post("/export", response_model=ExportResponse)
async def export_endpoint(req: ExportRequest) -> ExportResponse:
    """Export a model to a different format."""
    project_root = Path(req.project_root)
    source = Path(req.source) if Path(req.source).is_absolute() else project_root / req.source

    if not source.exists():
        return ExportResponse(success=False, error=f"Source file not found: {source}")

    try:
        from cadforge_engine.domain.sandbox import execute_cadquery

        # Load the source model and re-export
        if source.suffix.lower() in (".step", ".stp"):
            code = f'import cadquery as cq\nresult = cq.importers.importStep("{source}")'
        else:
            return ExportResponse(
                success=False,
                error=f"Cannot re-export from {source.suffix} format. Use ExecuteCadQuery to generate models.",
            )

        fmt = req.format
        output_dir = project_root / "output" / fmt
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / f"{req.name}.{fmt}"

        result = execute_cadquery(code, output_path=output_path)
        if result.success and result.has_workpiece:
            return ExportResponse(
                success=True,
                output_path=str(output_path),
                message=f"Exported to {output_path}",
            )
        return ExportResponse(success=False, error=result.error or "Export produced no output")

    except ImportError:
        return ExportResponse(success=False, error="CadQuery not installed")
    except Exception as e:
        return ExportResponse(success=False, error=str(e))
