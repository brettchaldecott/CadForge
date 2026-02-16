"""Tests for the CadForge agent loop."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from cadforge.chat.modes import InteractionMode, get_plan_mode_permissions
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


@pytest.fixture
def mock_agent(tmp_project):
    """Create an Agent with mocked LLM provider."""
    settings = CadForgeSettings(
        provider="ollama",
        model="test-model",
        base_url="http://localhost:11434/v1",
    )

    with patch("cadforge.core.agent.create_provider") as mock_create:
        mock_provider = MagicMock()
        mock_provider.call.return_value = {
            "content": [{"type": "text", "text": "Test response"}],
            "usage": {"input_tokens": 10, "output_tokens": 5},
        }
        mock_create.return_value = mock_provider

        agent = Agent(
            project_root=tmp_project,
            settings=settings,
        )
        agent._mock_provider = mock_provider
        yield agent


class TestAgentModes:
    def test_agent_mode_returns_str(self, mock_agent):
        result = mock_agent.process_message("hello", mode="agent")
        assert isinstance(result, str)
        assert result == "Test response"

    def test_plan_mode_returns_str(self, mock_agent):
        result = mock_agent.process_message("design a bracket", mode="plan")
        assert isinstance(result, str)

    def test_ask_mode_returns_str(self, mock_agent):
        result = mock_agent.process_message("what is PLA?", mode="ask")
        assert isinstance(result, str)

    def test_invalid_mode_defaults_to_agent(self, mock_agent):
        result = mock_agent.process_message("hello", mode="invalid")
        assert isinstance(result, str)

    def test_plan_mode_filters_tools(self, mock_agent):
        mock_agent.process_message("plan something", mode="plan")
        call_args = mock_agent._mock_provider.call.call_args
        tools = call_args[0][2]  # third positional arg
        tool_names = {t["name"] for t in tools}
        assert "ReadFile" in tool_names
        assert "ListFiles" in tool_names
        assert "SearchVault" in tool_names
        assert "WriteFile" not in tool_names
        assert "ExecuteCadQuery" not in tool_names

    def test_ask_mode_passes_empty_tools(self, mock_agent):
        mock_agent.process_message("question", mode="ask")
        call_args = mock_agent._mock_provider.call.call_args
        tools = call_args[0][2]
        assert tools == []

    def test_agent_mode_passes_all_tools(self, mock_agent):
        mock_agent.process_message("build something", mode="agent")
        call_args = mock_agent._mock_provider.call.call_args
        tools = call_args[0][2]
        tool_names = {t["name"] for t in tools}
        assert "WriteFile" in tool_names
        assert "ExecuteCadQuery" in tool_names
        assert "ReadFile" in tool_names

    def test_plan_mode_appends_system_prompt(self, mock_agent):
        mock_agent.process_message("plan", mode="plan")
        call_args = mock_agent._mock_provider.call.call_args
        system_prompt = call_args[0][1]
        assert "PLAN mode" in system_prompt
        assert "Read-only" in system_prompt

    def test_ask_mode_appends_system_prompt(self, mock_agent):
        mock_agent.process_message("ask", mode="ask")
        call_args = mock_agent._mock_provider.call.call_args
        system_prompt = call_args[0][1]
        assert "ASK mode" in system_prompt
        assert "No tools available" in system_prompt

    def test_plan_mode_swaps_permissions(self, mock_agent):
        original_perms = mock_agent.executor.permissions
        mock_agent.process_message("plan", mode="plan")
        # After call completes, permissions should be restored
        assert mock_agent.executor.permissions is original_perms

    def test_plan_mode_restores_permissions_on_error(self, mock_agent):
        original_perms = mock_agent.executor.permissions
        mock_agent._mock_provider.call.side_effect = RuntimeError("API error")
        with pytest.raises(RuntimeError):
            mock_agent.process_message("plan", mode="plan")
        assert mock_agent.executor.permissions is original_perms

    def test_default_mode_is_agent(self, mock_agent):
        mock_agent.process_message("hello")
        call_args = mock_agent._mock_provider.call.call_args
        tools = call_args[0][2]
        tool_names = {t["name"] for t in tools}
        # All tools should be present (agent mode)
        assert "WriteFile" in tool_names
        assert "ExecuteCadQuery" in tool_names
