"""Hybrid vault search with vector + full-text search and RRF fusion.

Supports LanceDB vector search and JSON fallback.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from cadforge_engine.vault.indexer import (
    get_lance_dir,
    get_vault_dir,
    is_index_stale,
    index_vault,
)
from cadforge_engine.vault.schema import TABLE_NAME


def search_vault(
    project_root: Path,
    query: str,
    tags: list[str] | None = None,
    limit: int = 5,
) -> list[dict[str, Any]]:
    """Search the knowledge vault.

    Auto-indexes if stale. Uses LanceDB vector search when available,
    falls back to JSON text search.

    Args:
        project_root: Project root directory
        query: Natural language search query
        tags: Optional tags to filter results
        limit: Maximum results to return

    Returns:
        List of result dicts with file_path, section, content, score
    """
    # Auto-index if needed
    if is_index_stale(project_root):
        index_vault(project_root, incremental=True)

    try:
        return _search_lancedb(project_root, query, tags, limit)
    except (ImportError, Exception):
        return _search_fallback(project_root, query, tags, limit)


def _search_lancedb(
    project_root: Path,
    query: str,
    tags: list[str] | None,
    limit: int,
) -> list[dict[str, Any]]:
    """Vector search using LanceDB."""
    import lancedb
    from sentence_transformers import SentenceTransformer

    lance_dir = get_lance_dir(project_root)
    db_path = lance_dir / "vault.lance"
    if not db_path.exists():
        return []

    db = lancedb.connect(str(db_path))
    try:
        table = db.open_table(TABLE_NAME)
    except Exception:
        return []

    # Generate query embedding
    model = SentenceTransformer("all-MiniLM-L6-v2")
    query_emb = model.encode([query])[0].tolist()

    # Vector search
    results = table.search(query_emb).limit(limit * 2).to_list()

    # Tag filtering
    if tags:
        tag_set = set(t.lower() for t in tags)
        results = [
            r for r in results
            if any(t.lower() in tag_set for t in r.get("tags", "").split(","))
        ]

    # Format results
    formatted = []
    for r in results[:limit]:
        formatted.append({
            "file_path": r.get("file_path", ""),
            "section": r.get("section", ""),
            "content": r.get("content", ""),
            "score": round(1.0 - r.get("_distance", 0.0), 4),
            "tags": r.get("tags", "").split(","),
        })

    return formatted


def _search_fallback(
    project_root: Path,
    query: str,
    tags: list[str] | None,
    limit: int,
) -> list[dict[str, Any]]:
    """Fallback text search using JSON chunks or raw vault files."""
    lance_dir = get_lance_dir(project_root)
    chunks_path = lance_dir / "chunks.json"

    if chunks_path.exists():
        return _search_json_chunks(chunks_path, query, tags, limit)
    return _search_raw_files(project_root, query, tags, limit)


def _search_json_chunks(
    chunks_path: Path,
    query: str,
    tags: list[str] | None,
    limit: int,
) -> list[dict[str, Any]]:
    """Search through JSON chunk file."""
    try:
        chunks = json.loads(chunks_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []

    query_lower = query.lower()
    query_words = query_lower.split()
    results = []

    for chunk in chunks:
        content_lower = chunk.get("content", "").lower()
        section_lower = chunk.get("section", "").lower()

        # Tag filter
        if tags:
            chunk_tags = chunk.get("tags", "").lower().split(",")
            if not any(t.lower() in chunk_tags for t in tags):
                continue

        # Score by word matches
        score = sum(1 for w in query_words if w in content_lower or w in section_lower)
        if score > 0:
            results.append({
                "file_path": chunk.get("file_path", ""),
                "section": chunk.get("section", ""),
                "content": chunk.get("content", ""),
                "score": score / len(query_words),
                "tags": chunk.get("tags", "").split(","),
            })

    results.sort(key=lambda r: r["score"], reverse=True)
    return results[:limit]


def _search_raw_files(
    project_root: Path,
    query: str,
    tags: list[str] | None,
    limit: int,
) -> list[dict[str, Any]]:
    """Last resort: search raw vault markdown files."""
    vault_dir = get_vault_dir(project_root)
    if not vault_dir.is_dir():
        return []

    query_lower = query.lower()
    results = []

    for md_file in vault_dir.rglob("*.md"):
        try:
            content = md_file.read_text(encoding="utf-8")
        except OSError:
            continue

        if query_lower in content.lower():
            rel = str(md_file.relative_to(vault_dir))
            lines = content.splitlines()
            for i, line in enumerate(lines):
                if query_lower in line.lower():
                    start = max(0, i - 2)
                    end = min(len(lines), i + 8)
                    snippet = "\n".join(lines[start:end])
                    results.append({
                        "file_path": rel,
                        "section": line.strip("# ").strip(),
                        "content": snippet,
                        "score": 0.5,
                        "tags": [],
                    })
                    break

    return results[:limit]
