"""Tests for the CadForge agent loop."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from cadforge.core.agent import Agent, build_system_prompt
from cadforge.config import CadForgeSettings


class TestBuildSystemPrompt:
    def test_includes_cadforge_identity(self, tmp_project: Path):
        settings = CadForgeSettings()
        prompt = build_system_prompt(tmp_project, settings)
        assert "CadForge" in prompt
        assert "CAD" in prompt

    def test_includes_memory(self, tmp_project: Path):
        settings = CadForgeSettings()
        prompt = build_system_prompt(tmp_project, settings)
        assert "Test Project" in prompt  # From CADFORGE.md

    def test_includes_printer_context(self, tmp_project: Path):
        # Create a printer profile
        printers_dir = tmp_project / "vault" / "printers"
        printers_dir.mkdir(parents=True)
        (printers_dir / "test-printer.md").write_text(
            "---\nname: Test Printer\nbuild_volume:\n  x: 200\n  y: 200\n  z: 200\n"
            "constraints:\n  min_wall_thickness: 0.8\n  max_overhang_angle: 45\n---\n"
            "# Test Printer\n"
        )
        settings = CadForgeSettings(printer="test-printer")
        prompt = build_system_prompt(tmp_project, settings)
        assert "200" in prompt
        assert "test-printer" in prompt

    def test_no_printer(self, tmp_project: Path):
        settings = CadForgeSettings(printer=None)
        prompt = build_system_prompt(tmp_project, settings)
        assert "Active printer" not in prompt

    def test_extra_context(self, tmp_project: Path):
        settings = CadForgeSettings()
        prompt = build_system_prompt(tmp_project, settings, extra_context="Custom context")
        assert "Custom context" in prompt


class TestAgent:
    def test_creates_agent(self, tmp_project: Path):
        agent = Agent(tmp_project)
        assert agent.project_root == tmp_project
        assert agent.session is not None
        assert agent.executor is not None

    def test_registers_all_handlers(self, tmp_project: Path):
        agent = Agent(tmp_project)
        expected_tools = [
            "ReadFile", "WriteFile", "ListFiles", "Bash",
            "SearchVault", "AnalyzeMesh", "ShowPreview",
            "ExecuteCadQuery", "GetPrinter", "ExportModel", "SearchWeb",
            "Task",
        ]
        for tool_name in expected_tools:
            assert tool_name in agent.executor._handlers, f"Missing handler: {tool_name}"

    def test_save_session(self, tmp_project: Path):
        agent = Agent(tmp_project)
        agent.session.add_user_message("test")
        agent.save_session()
        sessions = agent.session_index.list_sessions()
        assert len(sessions) == 1

    def test_process_message_without_api(self, tmp_project: Path):
        agent = Agent(tmp_project)
        # Without API key, should return an error/info message
        response = agent.process_message("hello")
        assert isinstance(response, str)
        assert len(response) > 0
