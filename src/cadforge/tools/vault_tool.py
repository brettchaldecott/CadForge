"""Vault search tool handler."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def handle_search_vault(
    tool_input: dict[str, Any],
    project_root: Path,
) -> dict[str, Any]:
    """Search the knowledge vault.

    Uses the vault search module for hybrid vector + FTS search.
    Falls back to simple file search if vault is not indexed.
    """
    query = tool_input["query"]
    tags = tool_input.get("tags", [])
    limit = tool_input.get("limit", 5)

    try:
        from cadforge.vault.search import search_vault
        results = search_vault(project_root, query, tags=tags, limit=limit)
        return {"success": True, "results": results, "query": query}
    except Exception:
        # Fallback: simple grep through vault markdown files
        return _fallback_search(project_root, query, limit)


def _fallback_search(
    project_root: Path,
    query: str,
    limit: int,
) -> dict[str, Any]:
    """Simple text search fallback when vault is not indexed."""
    vault_dir = project_root / "vault"
    if not vault_dir.is_dir():
        return {"success": True, "results": [], "query": query, "note": "No vault directory found"}

    results = []
    query_lower = query.lower()
    for md_file in vault_dir.rglob("*.md"):
        try:
            content = md_file.read_text(encoding="utf-8")
            if query_lower in content.lower():
                # Extract relevant section
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
                    results.append({
                        "file": str(md_file.relative_to(project_root)),
                        "snippet": snippet,
                        "score": 1.0,
                    })
        except Exception:
            continue

        if len(results) >= limit:
            break

    return {"success": True, "results": results, "query": query, "note": "fallback search"}
