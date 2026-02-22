"""Competitive multi-agent pipeline data models.

Tracks proposals from parallel agents, cross-critiques, fidelity scores,
competitive rounds, and the overall competitive design lifecycle.
Persists to .cadforge/competitive/{id}.json for crash-safe storage.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class ProposalStatus(str, Enum):
    """Lifecycle status of a single proposal."""
    PENDING = "pending"
    GENERATING = "generating"
    COMPLETED = "completed"
    FAILED = "failed"
    SELECTED = "selected"
    REJECTED = "rejected"


class CompetitiveDesignStatus(str, Enum):
    """Lifecycle status of a competitive design."""
    DRAFT = "draft"
    SUPERVISING = "supervising"
    PROPOSING = "proposing"
    DEBATING = "debating"
    EVALUATING = "evaluating"
    JUDGING = "judging"
    MERGING = "merging"
    AWAITING_APPROVAL = "awaiting_approval"
    LEARNING = "learning"
    COMPLETED = "completed"
    FAILED = "failed"


class CritiqueRecord(BaseModel):
    """A critique of one proposal by another model."""
    critic_model: str
    target_proposal_id: str
    strengths: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)
    suggested_fixes: list[str] = Field(default_factory=list)
    fidelity_concerns: list[str] = Field(default_factory=list)
    raw_text: str = ""
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class SandboxEvaluation(BaseModel):
    """Results from executing a proposal's code in the sandbox."""
    proposal_id: str
    execution_success: bool = False
    is_watertight: bool = False
    volume_mm3: float = 0.0
    surface_area_mm2: float = 0.0
    bounding_box: dict[str, float] = Field(default_factory=dict)
    center_of_mass: list[float] = Field(default_factory=list)
    dfm_issues: list[str] = Field(default_factory=list)
    execution_error: str | None = None
    stl_path: str | None = None
    png_paths: list[str] = Field(default_factory=list)
    geometric_diff: dict[str, float] = Field(default_factory=dict)


class FidelityScore(BaseModel):
    """Fidelity scoring result for a proposal."""
    proposal_id: str
    score: float = 0.0  # 0-100
    text_similarity: float = 0.0
    geometric_accuracy: float = 0.0
    manufacturing_viability: float = 0.0
    reasoning: str = ""
    passed: bool = False


class Proposal(BaseModel):
    """A single model's proposal within a competitive round."""
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    model: str
    code: str = ""
    reasoning: str = ""
    status: ProposalStatus = ProposalStatus.PENDING
    critiques_received: list[CritiqueRecord] = Field(default_factory=list)
    sandbox_eval: SandboxEvaluation | None = None
    fidelity_score: FidelityScore | None = None
    revision_code: str | None = None
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class CompetitiveRound(BaseModel):
    """A single competitive round with parallel proposals."""
    round_number: int
    proposals: list[Proposal] = Field(default_factory=list)
    winner_proposal_id: str | None = None
    merger_output: str | None = None
    merger_sandbox_eval: SandboxEvaluation | None = None
    human_approved: bool | None = None
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class CompetitiveDesignSpec(BaseModel):
    """A competitive design tracking the full multi-agent lifecycle."""
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    title: str = ""
    prompt: str = ""
    specification: str = ""
    constraints: dict[str, Any] = Field(default_factory=dict)
    kb_context: str = ""
    status: CompetitiveDesignStatus = CompetitiveDesignStatus.DRAFT
    rounds: list[CompetitiveRound] = Field(default_factory=list)
    final_code: str | None = None
    final_stl_path: str | None = None
    learnings_indexed: bool = False
    pipeline_config: dict[str, Any] = Field(default_factory=dict)
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class CompetitiveDesignStore:
    """File-based persistence at {project_root}/.cadforge/competitive/{id}.json."""

    def __init__(self, project_root: Path) -> None:
        self._dir = project_root / ".cadforge" / "competitive"
        self._dir.mkdir(parents=True, exist_ok=True)

    def _path(self, design_id: str) -> Path:
        return self._dir / f"{design_id}.json"

    def save(self, design: CompetitiveDesignSpec) -> None:
        """Persist a competitive design to disk."""
        design.updated_at = datetime.now(timezone.utc).isoformat()
        self._path(design.id).write_text(
            design.model_dump_json(indent=2) + "\n", encoding="utf-8"
        )

    def get(self, design_id: str) -> CompetitiveDesignSpec | None:
        """Load a competitive design by ID, or None if not found."""
        path = self._path(design_id)
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return CompetitiveDesignSpec(**data)
        except (json.JSONDecodeError, OSError, ValueError):
            return None

    def list_all(self) -> list[CompetitiveDesignSpec]:
        """List all stored competitive designs, sorted by creation time (newest first)."""
        designs = []
        for p in sorted(self._dir.glob("*.json"), reverse=True):
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                designs.append(CompetitiveDesignSpec(**data))
            except (json.JSONDecodeError, OSError, ValueError):
                continue
        return designs
