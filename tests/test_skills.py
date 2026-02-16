"""Tests for the CadForge skills system."""

from __future__ import annotations

from pathlib import Path

import pytest

from cadforge.skills.loader import (
    Skill,
    discover_skills,
    get_skill_by_name,
    get_slash_commands,
    load_skill,
)


@pytest.fixture
def skill_project(tmp_project: Path) -> Path:
    """Create a project with skills directories."""
    # Workspace skills
    ws_skills = tmp_project / "skills"
    ws_skills.mkdir(exist_ok=True)

    custom_skill = ws_skills / "custom-check"
    custom_skill.mkdir()
    (custom_skill / "SKILL.md").write_text(
        "---\nname: custom-check\ndescription: Custom skill\n"
        "allowed-tools: \"ReadFile, Bash\"\n---\n\n"
        "Run custom checks on the project.\n"
    )

    return tmp_project


class TestLoadSkill:
    def test_load_valid_skill(self, skill_project: Path):
        skill_dir = skill_project / "skills" / "custom-check"
        skill = load_skill(skill_dir)
        assert skill is not None
        assert skill.name == "custom-check"
        assert skill.description == "Custom skill"
        assert "ReadFile" in skill.allowed_tools
        assert "Bash" in skill.allowed_tools

    def test_load_missing_skill(self, tmp_path: Path):
        assert load_skill(tmp_path) is None

    def test_slash_command(self, skill_project: Path):
        skill_dir = skill_project / "skills" / "custom-check"
        skill = load_skill(skill_dir)
        assert skill.slash_command == "/custom-check"


class TestDiscoverSkills:
    def test_discovers_workspace_skills(self, skill_project: Path):
        skills = discover_skills(skill_project)
        names = [s.name for s in skills]
        assert "custom-check" in names

    def test_discovers_bundled_skills(self, tmp_project: Path):
        skills = discover_skills(tmp_project)
        names = [s.name for s in skills]
        assert "commit" in names
        assert "review" in names
        assert "dfm-check" in names

    def test_workspace_overrides_bundled(self, skill_project: Path):
        # Create a workspace skill that overrides bundled commit
        override_dir = skill_project / "skills" / "commit"
        override_dir.mkdir()
        (override_dir / "SKILL.md").write_text(
            "---\nname: commit\ndescription: Custom commit\n"
            "allowed-tools: \"Bash\"\n---\n\nCustom commit flow.\n"
        )

        skills = discover_skills(skill_project)
        commit_skills = [s for s in skills if s.name == "commit"]
        assert len(commit_skills) == 1
        assert commit_skills[0].description == "Custom commit"
        assert commit_skills[0].priority == 0  # Workspace priority


class TestGetSkillByName:
    def test_find_existing(self, skill_project: Path):
        skill = get_skill_by_name(skill_project, "custom-check")
        assert skill is not None
        assert skill.name == "custom-check"

    def test_find_missing(self, skill_project: Path):
        assert get_skill_by_name(skill_project, "nonexistent") is None


class TestGetSlashCommands:
    def test_returns_slash_commands(self, skill_project: Path):
        cmds = get_slash_commands(skill_project)
        assert "/custom-check" in cmds
        assert "/commit" in cmds
        assert "/dfm-check" in cmds
