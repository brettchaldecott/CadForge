"""LanceDB table schema for the knowledge vault."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


EMBEDDING_DIM = 384  # all-MiniLM-L6-v2
TABLE_NAME = "vault_chunks"


@dataclass
class VaultChunk:
    """A chunk of vault content for vector storage."""
    id: str
    file_path: str
    section: str
    content: str
    tags: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "file_path": self.file_path,
            "section": self.section,
            "content": self.content,
            "tags": ",".join(self.tags),
            "metadata": str(self.metadata),
        }
