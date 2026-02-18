"""Section-based markdown chunking for the knowledge vault.

Splits markdown files into sections based on headings,
preserving frontmatter metadata and creating chunks for indexing.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any

import yaml

from cadforge_engine.vault.schema import VaultChunk


def extract_frontmatter(content: str) -> tuple[dict[str, Any], str]:
    """Extract YAML frontmatter and body from markdown content.

    Returns (frontmatter_dict, body_text).
    """
    if not content.startswith("---"):
        return {}, content

    parts = content.split("---", 2)
    if len(parts) < 3:
        return {}, content

    try:
        fm = yaml.safe_load(parts[1]) or {}
    except yaml.YAMLError:
        fm = {}

    body = parts[2].lstrip("\n")
    return fm, body


def chunk_markdown(file_path: Path, base_dir: Path | None = None) -> list[VaultChunk]:
    """Split a markdown file into section-based chunks.

    Each top-level section (## heading) becomes a chunk.
    Content before the first heading is included as an 'overview' chunk.

    Args:
        file_path: Path to the markdown file
        base_dir: Base directory for relative path computation

    Returns:
        List of VaultChunk objects
    """
    content = file_path.read_text(encoding="utf-8")
    frontmatter, body = extract_frontmatter(content)

    tags = frontmatter.get("tags", [])
    if isinstance(tags, str):
        tags = [t.strip() for t in tags.split(",")]

    rel_path = str(file_path.relative_to(base_dir)) if base_dir else str(file_path)

    chunks = []
    sections = _split_sections(body)

    for section_title, section_content in sections:
        if not section_content.strip():
            continue

        chunk_id = _make_chunk_id(rel_path, section_title)
        chunks.append(VaultChunk(
            id=chunk_id,
            file_path=rel_path,
            section=section_title,
            content=section_content.strip(),
            tags=list(tags),
            metadata=frontmatter,
        ))

    return chunks


def _split_sections(body: str) -> list[tuple[str, str]]:
    """Split markdown body into (title, content) pairs by headings."""
    heading_pattern = re.compile(r"^(#{1,3})\s+(.+)$", re.MULTILINE)

    sections: list[tuple[str, str]] = []
    last_title = "Overview"
    last_pos = 0

    for match in heading_pattern.finditer(body):
        content = body[last_pos:match.start()]
        if content.strip():
            sections.append((last_title, content))

        last_title = match.group(2).strip()
        last_pos = match.end()

    # Remaining content
    remaining = body[last_pos:]
    if remaining.strip():
        sections.append((last_title, remaining))

    return sections


def _make_chunk_id(file_path: str, section: str) -> str:
    """Generate a deterministic chunk ID."""
    raw = f"{file_path}::{section}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]
