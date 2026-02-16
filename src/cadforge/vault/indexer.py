"""Vault indexer — converts markdown files to embeddings in LanceDB.

Supports full re-index and incremental (hash-based delta) indexing.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from cadforge.utils.paths import get_lance_dir, get_vault_dir
from cadforge.vault.chunker import chunk_markdown
from cadforge.vault.schema import TABLE_NAME


def compute_file_hash(path: Path) -> str:
    """Compute SHA256 hash of a file."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def get_manifest_path(project_root: Path) -> Path:
    """Path to the file hash manifest."""
    return get_lance_dir(project_root) / "manifest.json"


def load_manifest(project_root: Path) -> dict[str, str]:
    """Load the file hash manifest."""
    path = get_manifest_path(project_root)
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def save_manifest(project_root: Path, manifest: dict[str, str]) -> None:
    """Save the file hash manifest."""
    path = get_manifest_path(project_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


def get_vault_files(project_root: Path) -> list[Path]:
    """Get all markdown files in the vault directory."""
    vault_dir = get_vault_dir(project_root)
    if not vault_dir.is_dir():
        return []
    return sorted(vault_dir.rglob("*.md"))


def compute_current_hashes(project_root: Path) -> dict[str, str]:
    """Compute hashes for all current vault files."""
    vault_dir = get_vault_dir(project_root)
    hashes = {}
    for f in get_vault_files(project_root):
        rel = str(f.relative_to(vault_dir))
        hashes[rel] = compute_file_hash(f)
    return hashes


def find_changes(
    current: dict[str, str],
    previous: dict[str, str],
) -> tuple[list[str], list[str], list[str]]:
    """Find added, modified, and deleted files.

    Returns (added, modified, deleted) file lists.
    """
    added = [f for f in current if f not in previous]
    deleted = [f for f in previous if f not in current]
    modified = [
        f for f in current
        if f in previous and current[f] != previous[f]
    ]
    return added, modified, deleted


def index_vault(
    project_root: Path,
    incremental: bool = False,
) -> dict[str, Any]:
    """Index the vault into LanceDB.

    Args:
        project_root: Project root directory
        incremental: If True, only re-index changed files

    Returns:
        Dict with indexing stats
    """
    vault_dir = get_vault_dir(project_root)
    if not vault_dir.is_dir():
        return {"success": False, "error": "No vault directory found"}

    current_hashes = compute_current_hashes(project_root)
    previous_hashes = load_manifest(project_root) if incremental else {}

    if incremental:
        added, modified, deleted = find_changes(current_hashes, previous_hashes)
        files_to_index = added + modified
    else:
        files_to_index = list(current_hashes.keys())
        deleted = []

    # Chunk all files to index
    all_chunks = []
    for rel_path in files_to_index:
        full_path = vault_dir / rel_path
        if full_path.exists():
            chunks = chunk_markdown(full_path, base_dir=vault_dir)
            all_chunks.extend(chunks)

    # Try to use LanceDB + sentence-transformers for real indexing
    try:
        stats = _index_with_lancedb(project_root, all_chunks, deleted, not incremental)
    except ImportError:
        # Fallback: just save chunks as JSON for simple search
        stats = _index_fallback(project_root, all_chunks)

    # Save manifest
    save_manifest(project_root, current_hashes)

    return {
        "success": True,
        "files_indexed": len(files_to_index),
        "chunks_created": len(all_chunks),
        "files_deleted": len(deleted),
        **stats,
    }


def _index_with_lancedb(
    project_root: Path,
    chunks: list,
    deleted_files: list[str],
    full_rebuild: bool,
) -> dict[str, Any]:
    """Index using LanceDB and sentence-transformers."""
    import lancedb
    from sentence_transformers import SentenceTransformer

    lance_dir = get_lance_dir(project_root)
    db = lancedb.connect(str(lance_dir / "vault.lance"))

    # Generate embeddings
    model = SentenceTransformer("all-MiniLM-L6-v2")
    texts = [c.content for c in chunks]
    embeddings = model.encode(texts).tolist() if texts else []

    # Build records
    records = []
    for chunk, emb in zip(chunks, embeddings):
        records.append({
            "id": chunk.id,
            "file_path": chunk.file_path,
            "section": chunk.section,
            "content": chunk.content,
            "tags": ",".join(chunk.tags),
            "vector": emb,
        })

    if full_rebuild and records:
        table = db.create_table(TABLE_NAME, records, mode="overwrite")
    elif records:
        try:
            table = db.open_table(TABLE_NAME)
            table.add(records)
        except Exception:
            table = db.create_table(TABLE_NAME, records, mode="overwrite")

    return {"backend": "lancedb"}


def _index_fallback(project_root: Path, chunks: list) -> dict[str, Any]:
    """Fallback: save chunks as JSON for simple text search."""
    lance_dir = get_lance_dir(project_root)
    chunks_path = lance_dir / "chunks.json"

    records = [c.to_dict() for c in chunks]
    chunks_path.write_text(json.dumps(records, indent=2), encoding="utf-8")

    return {"backend": "json_fallback"}


def is_index_stale(project_root: Path) -> bool:
    """Check if the vault index needs updating."""
    current = compute_current_hashes(project_root)
    previous = load_manifest(project_root)
    if not previous:
        return True
    added, modified, deleted = find_changes(current, previous)
    return bool(added or modified or deleted)
