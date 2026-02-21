"""Pydantic request models for the CadForge engine API."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class CadQueryRequest(BaseModel):
    """Request to execute CadQuery code."""
    code: str = Field(..., description="CadQuery Python code to execute")
    output_name: str = Field(default="model", description="Output filename (without extension)")
    format: str = Field(default="stl", pattern="^(stl|step)$", description="Export format")
    project_root: str = Field(..., description="Project root directory path")


class MeshAnalyzeRequest(BaseModel):
    """Request to analyze a mesh file."""
    path: str = Field(..., description="Path to the mesh file (absolute or relative to project_root)")
    project_root: str = Field(..., description="Project root directory path")


class PreviewRequest(BaseModel):
    """Request to launch 3D preview."""
    path: str = Field(..., description="Path to the STL file")
    color: str = Field(default="lightblue", description="Mesh color")
    background: str = Field(default="white", description="Background color")


class ExportRequest(BaseModel):
    """Request to export a model to a different format."""
    source: str = Field(..., description="Path to the source model file")
    format: str = Field(default="step", pattern="^(stl|step|3mf)$", description="Target export format")
    name: str = Field(default="model", description="Output filename (without extension)")
    project_root: str = Field(..., description="Project root directory path")


class VaultSearchRequest(BaseModel):
    """Request to search the knowledge vault."""
    query: str = Field(..., description="Natural language search query")
    tags: list[str] = Field(default_factory=list, description="Optional tags to filter results")
    limit: int = Field(default=5, ge=1, le=50, description="Maximum results to return")
    project_root: str = Field(..., description="Project root directory path")


class VaultIndexRequest(BaseModel):
    """Request to index the vault."""
    project_root: str = Field(..., description="Project root directory path")
    incremental: bool = Field(default=False, description="Only re-index changed files")


class CadSubagentProviderConfig(BaseModel):
    """Provider configuration forwarded from the Node CLI."""
    provider: Literal["anthropic", "openai", "ollama", "bedrock"] = "anthropic"
    api_key: str | None = None
    auth_token: str | None = None
    base_url: str | None = None
    aws_region: str | None = None
    aws_profile: str | None = None


class CadSubagentRequest(BaseModel):
    """Request to run the CAD subagent."""
    prompt: str = Field(..., description="Task prompt for the CAD subagent")
    context: str = Field(default="", description="Additional context")
    project_root: str = Field(..., description="Project root directory path")
    auth: dict = Field(default_factory=dict, description="Forwarded auth credentials (deprecated)")
    provider_config: CadSubagentProviderConfig | None = Field(
        default=None, description="Provider configuration (preferred over auth)"
    )
    model: str = Field(default="claude-sonnet-4-5-20250929", description="Model to use")
    max_tokens: int = Field(default=8192, description="Max tokens per LLM call")
