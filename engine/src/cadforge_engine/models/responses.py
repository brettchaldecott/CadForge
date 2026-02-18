"""Pydantic response models for the CadForge engine API."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    """Health check response."""
    status: str = "ok"
    version: str
    capabilities: list[str] = Field(default_factory=list)


class CadQueryResponse(BaseModel):
    """Response from CadQuery execution."""
    success: bool
    stdout: str = ""
    stderr: str = ""
    error: str | None = None
    output_path: str | None = None
    script_path: str | None = None
    message: str | None = None


class MeshAnalysisResponse(BaseModel):
    """Response from mesh analysis."""
    success: bool
    error: str | None = None
    file_path: str | None = None
    is_watertight: bool | None = None
    volume_mm3: float | None = None
    volume_cm3: float | None = None
    surface_area_mm2: float | None = None
    triangle_count: int | None = None
    vertex_count: int | None = None
    bounding_box: dict[str, float] | None = None
    center_of_mass: list[float] | None = None
    issues: list[str] | None = None


class PreviewResponse(BaseModel):
    """Response from preview launch."""
    success: bool
    message: str | None = None
    error: str | None = None


class ExportResponse(BaseModel):
    """Response from model export."""
    success: bool
    output_path: str | None = None
    message: str | None = None
    error: str | None = None


class VaultSearchResult(BaseModel):
    """A single vault search result."""
    file_path: str
    section: str
    content: str
    score: float
    tags: list[str] = Field(default_factory=list)


class VaultSearchResponse(BaseModel):
    """Response from vault search."""
    success: bool
    query: str
    results: list[VaultSearchResult] = Field(default_factory=list)
    note: str | None = None
    error: str | None = None


class VaultIndexResponse(BaseModel):
    """Response from vault indexing."""
    success: bool
    files_indexed: int = 0
    chunks_created: int = 0
    files_deleted: int = 0
    backend: str | None = None
    error: str | None = None
