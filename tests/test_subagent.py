"""Tests for sub-agent executor and task tool."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from cadforge.config import CadForgeSettings
from cadforge.core.subagent import SubagentConfig, SubagentResult, create_subagent_config
from cadforge.core.subagent_executor import _filter_tools, run_subagent
from cadforge.tools.registry import get_tool_definitions, get_tool_names


def _make_text_response(text: str) -> dict[str, Any]:
    """Build a mock LLM response with text only."""
    return {
        "content": [{"type": "text", "text": text}],
        "usage": {"input_tokens": 10, "output_tokens": 20},
    }


def _make_tool_response(tool_name: str, tool_id: str, tool_input: dict) -> dict[str, Any]:
    """Build a mock LLM response with a tool_use block."""
    return {
        "content": [
            {"type": "tool_use", "id": tool_id, "name": tool_name, "input": tool_input},
        ],
        "usage": {"input_tokens": 10, "output_tokens": 20},
    }


class TestFilterTools:
    def test_filters_to_allowed(self):
        filtered = _filter_tools(["ReadFile", "ListFiles"])
        names = {t["name"] for t in filtered}
        assert names == {"ReadFile", "ListFiles"}

    def test_excludes_task(self):
        filtered = _filter_tools(["ReadFile", "Task", "ListFiles"])
        names = {t["name"] for t in filtered}
        assert "Task" not in names
        assert "ReadFile" in names
        assert "ListFiles" in names

    def test_empty_list(self):
        filtered = _filter_tools([])
        assert filtered == []

    def test_unknown_tool_ignored(self):
        filtered = _filter_tools(["ReadFile", "NonexistentTool"])
        names = {t["name"] for t in filtered}
        assert names == {"ReadFile"}


class TestRunSubagent:
    @pytest.fixture
    def mock_provider(self):
        return MagicMock()

    @pytest.fixture
    def settings(self):
        return CadForgeSettings()

    @pytest.fixture
    def permissions(self):
        return {
            "deny": [],
            "allow": ["ReadFile(*)", "ListFiles(*)", "SearchVault(*)", "Bash(*)"],
            "ask": [],
        }

    def test_text_only_response(self, tmp_project, mock_provider, settings, permissions):
        """Provider returns text without tools — should return immediately."""
        mock_provider.call.return_value = _make_text_response("Found 12 files.")

        config = SubagentConfig.explore()
        result = run_subagent(
            config, "Find all Python files", "",
            mock_provider, settings, tmp_project, permissions, lambda _: True,
        )

        assert result.success is True
        assert "Found 12 files" in result.output
        assert result.agent_name == "explore"
        assert result.error is None
        assert mock_provider.call.call_count == 1

    def test_with_tools(self, tmp_project, mock_provider, settings, permissions):
        """Provider returns tool_use then text — tools executed, output returned."""
        # First call: tool_use for ReadFile
        mock_provider.call.side_effect = [
            _make_tool_response("ReadFile", "call_1", {"path": "test.txt"}),
            _make_text_response("The file contains test data."),
        ]

        # Create the file so ReadFile handler works
        (tmp_project / "test.txt").write_text("hello world")

        config = SubagentConfig.explore()
        result = run_subagent(
            config, "Read test.txt", "",
            mock_provider, settings, tmp_project, permissions, lambda _: True,
        )

        assert result.success is True
        assert "test data" in result.output
        assert mock_provider.call.call_count == 2

    def test_max_iterations(self, tmp_project, mock_provider, settings, permissions):
        """Provider always returns tool_use — should hit max iterations."""
        # Always return a tool call
        mock_provider.call.return_value = _make_tool_response(
            "ReadFile", "call_loop", {"path": "test.txt"}
        )
        (tmp_project / "test.txt").write_text("data")

        config = SubagentConfig.explore()
        config.max_iterations = 3
        result = run_subagent(
            config, "Keep reading", "",
            mock_provider, settings, tmp_project, permissions, lambda _: True,
        )

        assert result.success is True
        assert "max iterations" in result.output.lower()
        assert mock_provider.call.call_count == 3

    def test_none_response(self, tmp_project, mock_provider, settings, permissions):
        """Provider returns None — should return error."""
        mock_provider.call.return_value = None

        config = SubagentConfig.explore()
        result = run_subagent(
            config, "Do something", "",
            mock_provider, settings, tmp_project, permissions, lambda _: True,
        )

        assert result.success is False
        assert result.error is not None
        assert "Failed" in result.error

    def test_context_included(self, tmp_project, mock_provider, settings, permissions):
        """Context is prepended to the task prompt in messages."""
        mock_provider.call.return_value = _make_text_response("Done.")

        config = SubagentConfig.explore()
        run_subagent(
            config, "Find files", "Project uses Python 3.12",
            mock_provider, settings, tmp_project, permissions, lambda _: True,
        )

        # Check that the first message includes both context and prompt
        call_args = mock_provider.call.call_args
        messages = call_args[0][0]
        assert "Python 3.12" in messages[0]["content"]
        assert "Find files" in messages[0]["content"]

    def test_no_task_tool_in_subagent(self, tmp_project, mock_provider, settings, permissions):
        """Verify Task is filtered from sub-agent tool definitions."""
        mock_provider.call.return_value = _make_text_response("Done.")

        config = SubagentConfig.explore()
        run_subagent(
            config, "Search", "",
            mock_provider, settings, tmp_project, permissions, lambda _: True,
        )

        # Check the tools passed to provider.call
        call_args = mock_provider.call.call_args
        tools = call_args[0][2]  # Third positional arg is tools
        tool_names = {t["name"] for t in tools}
        assert "Task" not in tool_names


class TestHandleTask:
    @pytest.fixture
    def mock_agent(self, tmp_project):
        """Create a mock Agent with required attributes."""
        agent = MagicMock()
        agent.project_root = tmp_project
        agent.settings = CadForgeSettings()
        agent.ask_callback = lambda _: True
        agent._provider = MagicMock()
        agent._provider.call.return_value = _make_text_response("Exploration complete.")
        return agent

    def test_explore(self, mock_agent):
        from cadforge.tools.task_tool import handle_task

        result = handle_task(
            {"agent_type": "explore", "prompt": "Find CadQuery files"},
            mock_agent,
        )
        assert result["success"] is True
        assert "Exploration complete" in result["output"]
        assert result["agent_name"] == "explore"
        assert result["error"] is None

    def test_plan(self, mock_agent):
        from cadforge.tools.task_tool import handle_task

        mock_agent._provider.call.return_value = _make_text_response("Plan ready.")
        result = handle_task(
            {"agent_type": "plan", "prompt": "Design auth system"},
            mock_agent,
        )
        assert result["success"] is True
        assert result["agent_name"] == "plan"

    def test_invalid_type(self, mock_agent):
        from cadforge.tools.task_tool import handle_task

        result = handle_task(
            {"agent_type": "invalid", "prompt": "Do something"},
            mock_agent,
        )
        assert result["success"] is False
        assert "Invalid agent_type" in result["error"]

    def test_custom_type_rejected(self, mock_agent):
        from cadforge.tools.task_tool import handle_task

        result = handle_task(
            {"agent_type": "custom", "prompt": "Do something"},
            mock_agent,
        )
        assert result["success"] is False
        assert "Invalid agent_type" in result["error"]

    def test_missing_prompt(self, mock_agent):
        from cadforge.tools.task_tool import handle_task

        result = handle_task(
            {"agent_type": "explore", "prompt": ""},
            mock_agent,
        )
        assert result["success"] is False
        assert "required" in result["error"]

    def test_with_context(self, mock_agent):
        from cadforge.tools.task_tool import handle_task

        result = handle_task(
            {
                "agent_type": "explore",
                "prompt": "Find files",
                "context": "Using CadQuery 2.4",
            },
            mock_agent,
        )
        assert result["success"] is True


class TestTaskToolInRegistry:
    def test_task_tool_exists(self):
        names = get_tool_names()
        assert "Task" in names

    def test_task_tool_schema(self):
        tools = get_tool_definitions()
        task_tool = next(t for t in tools if t["name"] == "Task")
        schema = task_tool["input_schema"]
        assert "agent_type" in schema["properties"]
        assert "prompt" in schema["properties"]
        assert "context" in schema["properties"]
        assert schema["properties"]["agent_type"]["enum"] == ["explore", "plan", "cad"]
        assert "agent_type" in schema["required"]
        assert "prompt" in schema["required"]
