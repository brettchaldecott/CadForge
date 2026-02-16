"""Shared test fixtures for CadForge."""

from __future__ import annotations

import json
from pathlib import Path

import pytest


@pytest.fixture
def tmp_project(tmp_path: Path) -> Path:
    """Create a temporary CadForge project structure."""
    (tmp_path / "CADFORGE.md").write_text("# Test Project\n")
    cadforge_dir = tmp_path / ".cadforge"
    cadforge_dir.mkdir()
    memory_dir = cadforge_dir / "memory"
    memory_dir.mkdir()
    (memory_dir / "MEMORY.md").write_text("# Auto Memory\n")
    (cadforge_dir / "settings.json").write_text(json.dumps({
        "permissions": {
            "deny": ["Bash(rm:*)"],
            "allow": ["ReadFile(*)"],
            "ask": ["WriteFile(*)"],
        },
        "hooks": [],
    }))
    (tmp_path / "vault").mkdir()
    (tmp_path / "output").mkdir()
    (tmp_path / "skills").mkdir()
    return tmp_path


@pytest.fixture
def tmp_settings_path(tmp_path: Path) -> Path:
    """Return a path for a temporary settings.json."""
    return tmp_path / "settings.json"
