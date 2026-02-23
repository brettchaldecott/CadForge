"""Design specification model and file-based persistence.

Tracks the full lifecycle of a design: draft → approved → executing → completed | failed.
Each iteration round captures code, STL path, rendered PNGs, and judge verdict.
Persists to .cadforge/designs/{id}.json for crash-safe, human-readable storage.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class DesignStatus(str, Enum):
    """Design lifecycle status."""
    DRAFT = "draft"
    APPROVED = "approved"
    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"


class IterationRecord(BaseModel):
    """Record of a single design-code-render-judge round."""
    round_number: int
    code: str = ""
    stl_path: str | None = None
    png_paths: list[str] = Field(default_factory=list)
    verdict: str = ""
    approved: bool = False
    errors: list[str] = Field(default_factory=list)
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class DesignSpec(BaseModel):
    """A persistent design document tracking the full lifecycle."""
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    title: str = ""
    prompt: str = ""
    specification: str = ""
    constraints: dict[str, Any] = Field(default_factory=dict)
    status: DesignStatus = DesignStatus.DRAFT
    iterations: list[IterationRecord] = Field(default_factory=list)
    final_output_path: str | None = None
    learnings_indexed: bool = False
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class DesignStore:
    """File-based design persistence at {project_root}/.cadforge/designs/{id}.json."""

    def __init__(self, project_root: Path) -> None:
        self._dir = project_root / ".cadforge" / "designs"
        self._dir.mkdir(parents=True, exist_ok=True)

    def _path(self, design_id: str) -> Path:
        return self._dir / f"{design_id}.json"

    def save(self, design: DesignSpec) -> None:
        """Persist a design to disk."""
        design.updated_at = datetime.now(timezone.utc).isoformat()
        self._path(design.id).write_text(
            design.model_dump_json(indent=2) + "\n", encoding="utf-8"
        )

    def get(self, design_id: str) -> DesignSpec | None:
        """Load a design by ID, or None if not found."""
        path = self._path(design_id)
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return DesignSpec(**data)
        except (json.JSONDecodeError, OSError, ValueError):
            return None

    def list_all(self) -> list[DesignSpec]:
        """List all stored designs, sorted by creation time (newest first)."""
        designs = []
        for p in sorted(self._dir.glob("*.json"), reverse=True):
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                designs.append(DesignSpec(**data))
            except (json.JSONDecodeError, OSError, ValueError):
                continue
        return designs

    def delete(self, design_id: str) -> bool:
        """Delete a design. Returns True if deleted, False if not found."""
        path = self._path(design_id)
        if path.exists():
            path.unlink()
            return True
        return False
