"""Vault search and indexing endpoints."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter

from pydantic import BaseModel, Field

from cadforge_engine.models.requests import VaultSearchRequest, VaultIndexRequest
from cadforge_engine.models.responses import (
    VaultSearchResponse,
    VaultSearchResult,
    VaultIndexResponse,
)

router = APIRouter(prefix="/vault")


@router.post("/search", response_model=VaultSearchResponse)
async def search_vault_endpoint(req: VaultSearchRequest) -> VaultSearchResponse:
    """Search the knowledge vault."""
    project_root = Path(req.project_root)

    try:
        from cadforge_engine.vault.search import search_vault
        results = search_vault(project_root, req.query, tags=req.tags or None, limit=req.limit)
        return VaultSearchResponse(
            success=True,
            query=req.query,
            results=[VaultSearchResult(**r) for r in results],
        )
    except Exception as e:
        # Fallback to simple file search
        return _fallback_search(project_root, req.query, req.limit, error=str(e))


def _fallback_search(
    project_root: Path,
    query: str,
    limit: int,
    error: str | None = None,
) -> VaultSearchResponse:
    """Simple text search fallback."""
    vault_dir = project_root / "vault"
    if not vault_dir.is_dir():
        return VaultSearchResponse(
            success=True,
            query=query,
            results=[],
            note="No vault directory found",
        )

    results = []
    query_lower = query.lower()
    for md_file in vault_dir.rglob("*.md"):
        try:
            content = md_file.read_text(encoding="utf-8")
            if query_lower in content.lower():
                lines = content.splitlines()
                matching_lines = [
                    (i, line) for i, line in enumerate(lines)
                    if query_lower in line.lower()
                ]
                if matching_lines:
                    idx = matching_lines[0][0]
                    start = max(0, idx - 2)
                    end = min(len(lines), idx + 5)
                    snippet = "\n".join(lines[start:end])
                    results.append(VaultSearchResult(
                        file_path=str(md_file.relative_to(project_root)),
                        section=matching_lines[0][1].strip("# ").strip(),
                        content=snippet,
                        score=1.0,
                        tags=[],
                    ))
        except Exception:
            continue

        if len(results) >= limit:
            break

    return VaultSearchResponse(
        success=True,
        query=query,
        results=results,
        note="fallback search" + (f" (original error: {error})" if error else ""),
    )


class VaultIngestUrlsRequest(BaseModel):
    """Request to ingest documentation URLs into the vault."""
    urls: list[str] = Field(..., description="URLs to scrape")
    source_name: str = Field(..., description="Name identifying the documentation source")
    project_root: str = Field(..., description="Project root directory path")


class VaultIngestUrlsResponse(BaseModel):
    """Response from URL ingestion."""
    success: bool
    urls_scraped: int = 0
    chunks_created: int = 0
    error: str | None = None


@router.post("/ingest-urls", response_model=VaultIngestUrlsResponse)
async def ingest_urls_endpoint(req: VaultIngestUrlsRequest) -> VaultIngestUrlsResponse:
    """Scrape documentation URLs and index into the vault."""
    project_root = Path(req.project_root)

    try:
        from cadforge_engine.vault.scraper import scrape_documentation
        from cadforge_engine.vault.indexer import index_urls

        chunks = scrape_documentation(req.urls, req.source_name)
        stats = index_urls(project_root, chunks)

        return VaultIngestUrlsResponse(
            success=True,
            urls_scraped=len(req.urls),
            chunks_created=stats.get("chunks_created", 0),
        )
    except ImportError as e:
        return VaultIngestUrlsResponse(
            success=False,
            error=f"Missing dependencies (httpx, beautifulsoup4): {e}",
        )
    except Exception as e:
        return VaultIngestUrlsResponse(success=False, error=str(e))


@router.post("/index", response_model=VaultIndexResponse)
async def index_vault_endpoint(req: VaultIndexRequest) -> VaultIndexResponse:
    """Index the vault for search."""
    project_root = Path(req.project_root)

    try:
        from cadforge_engine.vault.indexer import index_vault
        stats = index_vault(project_root, incremental=req.incremental)
        return VaultIndexResponse(**stats)
    except Exception as e:
        return VaultIndexResponse(success=False, error=str(e))
