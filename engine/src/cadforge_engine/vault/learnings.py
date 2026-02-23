"""Learning extraction from completed designs.

After a design pipeline completes, extracts structured learning chunks
(successful patterns, error patterns, refinement feedback, geometric patterns)
and formats them as VaultChunk objects for indexing into the vault.
"""

from __future__ import annotations

import hashlib

from cadforge_engine.models.designs import DesignSpec
from cadforge_engine.vault.schema import VaultChunk


def _make_learning_id(design_id: str, learning_type: str, suffix: str = "") -> str:
    """Generate a deterministic chunk ID for a learning."""
    raw = f"learning:{design_id}:{learning_type}:{suffix}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def extract_learnings(design: DesignSpec) -> list[VaultChunk]:
    """Extract learning chunks from a completed design.

    Produces up to 4 types of chunks:
    1. Successful code pattern — from the approved iteration
    2. Error patterns — from failed iterations
    3. Refinement feedback — judge feedback that led to improvements
    4. Geometric pattern — high-level prompt→geometry mapping
    """
    chunks: list[VaultChunk] = []
    file_path = f"learnings/design-{design.id}.md"
    prompt_excerpt = design.prompt[:200] if design.prompt else ""

    # 1. Successful code pattern
    approved_iterations = [it for it in design.iterations if it.approved]
    if approved_iterations:
        it = approved_iterations[-1]
        content = (
            f"# Successful CAD Pattern\n\n"
            f"**Prompt:** {prompt_excerpt}\n\n"
            f"**Specification excerpt:** {design.specification[:300]}\n\n"
            f"**Working code (round {it.round_number}):**\n```python\n{it.code}\n```\n\n"
            f"**Rounds needed:** {it.round_number}\n"
        )
        chunks.append(VaultChunk(
            id=_make_learning_id(design.id, "successful"),
            file_path=file_path,
            section="Successful Code Pattern",
            content=content,
            tags=["learning", "cad-pattern", "successful"],
            metadata={
                "design_id": design.id,
                "learning_type": "successful_pattern",
                "prompt": prompt_excerpt,
            },
        ))

    # 2. Error patterns — from failed iterations
    failed_iterations = [it for it in design.iterations if not it.approved and it.errors]
    for it in failed_iterations:
        code_snippet = it.code[:500] if it.code else "(no code)"
        error_summary = "; ".join(it.errors[:3])
        content = (
            f"# Error Pattern\n\n"
            f"**Prompt:** {prompt_excerpt}\n\n"
            f"**Code attempted (round {it.round_number}):**\n```python\n{code_snippet}\n```\n\n"
            f"**Errors:** {error_summary}\n"
        )
        chunks.append(VaultChunk(
            id=_make_learning_id(design.id, "error", str(it.round_number)),
            file_path=file_path,
            section=f"Error Pattern (round {it.round_number})",
            content=content,
            tags=["learning", "error-pattern"],
            metadata={
                "design_id": design.id,
                "learning_type": "error_pattern",
                "prompt": prompt_excerpt,
                "round": it.round_number,
            },
        ))

    # 3. Refinement feedback — judge feedback from non-final rounds
    refinement_iterations = [
        it for it in design.iterations
        if not it.approved and it.verdict and not it.verdict.upper().startswith("APPROVED")
    ]
    for it in refinement_iterations:
        content = (
            f"# Refinement Feedback\n\n"
            f"**Prompt:** {prompt_excerpt}\n\n"
            f"**Round {it.round_number} judge feedback:**\n{it.verdict}\n\n"
            f"This feedback was used to improve the model in subsequent rounds.\n"
        )
        chunks.append(VaultChunk(
            id=_make_learning_id(design.id, "refinement", str(it.round_number)),
            file_path=file_path,
            section=f"Refinement Feedback (round {it.round_number})",
            content=content,
            tags=["learning", "judge-feedback", "refinement"],
            metadata={
                "design_id": design.id,
                "learning_type": "refinement_feedback",
                "prompt": prompt_excerpt,
                "round": it.round_number,
            },
        ))

    # 4. Geometric pattern — high-level prompt→geometry summary
    if approved_iterations and design.specification:
        content = (
            f"# Geometric Pattern\n\n"
            f"**User request:** {prompt_excerpt}\n\n"
            f"**Geometric specification:**\n{design.specification[:500]}\n\n"
            f"**Result:** Successfully generated in {len(design.iterations)} round(s).\n"
            f"**Title:** {design.title}\n"
        )
        chunks.append(VaultChunk(
            id=_make_learning_id(design.id, "geometric"),
            file_path=file_path,
            section="Geometric Pattern",
            content=content,
            tags=["learning", "geometric-pattern"],
            metadata={
                "design_id": design.id,
                "learning_type": "geometric_pattern",
                "prompt": prompt_excerpt,
            },
        ))

    return chunks
