"""Tests for CadForge tool registry, executor, and handlers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from cadforge.tools.registry import (
    get_tool_definition,
    get_tool_definitions,
    get_tool_names,
)
from cadforge.tools.executor import ToolExecutor, _extract_permission_arg
from cadforge.tools.file_tool import handle_list_files, handle_read_file, handle_write_file
from cadforge.tools.bash_tool import handle_bash
from cadforge.tools.project_tool import _extract_frontmatter


class TestToolRegistry:
    def test_has_all_tools(self):
        names = get_tool_names()
        expected = [
            "ExecuteCadQuery", "ReadFile", "WriteFile", "ListFiles",
            "SearchVault", "AnalyzeMesh", "ShowPreview", "ExportModel",
            "Bash", "GetPrinter", "SearchWeb",
        ]
        for name in expected:
            assert name in names, f"Missing tool: {name}"

    def test_tool_definitions_valid(self):
        tools = get_tool_definitions()
        for tool in tools:
            assert "name" in tool
            assert "description" in tool
            assert "input_schema" in tool
            assert tool["input_schema"]["type"] == "object"

    def test_get_specific_tool(self):
        tool = get_tool_definition("ExecuteCadQuery")
        assert tool is not None
        assert tool["name"] == "ExecuteCadQuery"
        assert "code" in tool["input_schema"]["properties"]

    def test_get_nonexistent_tool(self):
        assert get_tool_definition("Nonexistent") is None


class TestExtractPermissionArg:
    def test_bash_command(self):
        arg = _extract_permission_arg("Bash", {"command": "git status"})
        assert arg == "git:status"

    def test_bash_single_word(self):
        arg = _extract_permission_arg("Bash", {"command": "ls"})
        assert arg == "ls"

    def test_read_file(self):
        arg = _extract_permission_arg("ReadFile", {"path": "src/main.py"})
        assert arg == "src/main.py"

    def test_cadquery(self):
        arg = _extract_permission_arg("ExecuteCadQuery", {"output_name": "cube"})
        assert arg == "cube"

    def test_unknown_tool(self):
        arg = _extract_permission_arg("Unknown", {})
        assert arg == "*"


class TestToolExecutor:
    @pytest.fixture
    def executor(self, tmp_project: Path) -> ToolExecutor:
        permissions = {
            "deny": ["Bash(rm:*)"],
            "allow": ["ReadFile(*)"],
            "ask": ["WriteFile(*)"],
        }
        ex = ToolExecutor(
            project_root=tmp_project,
            permissions=permissions,
            ask_callback=lambda _: True,  # Auto-approve asks
        )
        # Register a simple test handler
        ex.register_handler("ReadFile", lambda inp: {"content": "test"})
        ex.register_handler("WriteFile", lambda inp: {"written": True})
        ex.register_handler("Bash", lambda inp: {"output": "ok"})
        return ex

    def test_allowed_tool(self, executor: ToolExecutor):
        result = executor.execute("ReadFile", {"path": "test.py"})
        assert result["success"] is True
        assert result["blocked"] is False

    def test_denied_tool(self, executor: ToolExecutor):
        result = executor.execute("Bash", {"command": "rm -rf /"})
        assert result["success"] is False
        assert result["blocked"] is True
        assert "denied" in result["error"].lower()

    def test_ask_approved(self, executor: ToolExecutor):
        result = executor.execute("WriteFile", {"path": "test.py", "content": "x"})
        assert result["success"] is True

    def test_ask_denied(self, tmp_project: Path):
        ex = ToolExecutor(
            project_root=tmp_project,
            permissions={"deny": [], "allow": [], "ask": ["WriteFile(*)"]},
            ask_callback=lambda _: False,  # Deny all
        )
        ex.register_handler("WriteFile", lambda inp: {"written": True})
        result = ex.execute("WriteFile", {"path": "test.py", "content": "x"})
        assert result["success"] is False
        assert result["blocked"] is True

    def test_no_handler(self, executor: ToolExecutor):
        result = executor.execute("UnknownTool", {})
        assert result["success"] is False
        assert "No handler" in result["error"]

    def test_handler_exception(self, tmp_project: Path):
        ex = ToolExecutor(
            project_root=tmp_project,
            permissions={"deny": [], "allow": ["Failing(*)"], "ask": []},
        )
        ex.register_handler("Failing", lambda inp: 1 / 0)
        result = ex.execute("Failing", {})
        assert result["success"] is False
        assert "division" in result["error"].lower()


class TestFileToolHandlers:
    def test_read_file(self, tmp_project: Path):
        (tmp_project / "test.txt").write_text("hello world")
        result = handle_read_file({"path": "test.txt"}, tmp_project)
        assert result["success"] is True
        assert result["content"] == "hello world"

    def test_read_missing_file(self, tmp_project: Path):
        result = handle_read_file({"path": "missing.txt"}, tmp_project)
        assert result["success"] is False

    def test_write_file(self, tmp_project: Path):
        result = handle_write_file(
            {"path": "new.txt", "content": "test content"},
            tmp_project,
        )
        assert result["success"] is True
        assert (tmp_project / "new.txt").read_text() == "test content"

    def test_write_creates_dirs(self, tmp_project: Path):
        result = handle_write_file(
            {"path": "sub/dir/file.txt", "content": "nested"},
            tmp_project,
        )
        assert result["success"] is True
        assert (tmp_project / "sub" / "dir" / "file.txt").read_text() == "nested"

    def test_list_files(self, tmp_project: Path):
        (tmp_project / "a.py").write_text("x")
        (tmp_project / "b.py").write_text("y")
        result = handle_list_files({"pattern": "*.py"}, tmp_project)
        assert result["success"] is True
        assert "a.py" in result["files"]
        assert "b.py" in result["files"]


class TestBashHandler:
    def test_echo(self, tmp_project: Path):
        result = handle_bash({"command": "echo hello"}, tmp_project)
        assert result["success"] is True
        assert "hello" in result["stdout"]

    def test_failing_command(self, tmp_project: Path):
        result = handle_bash({"command": "exit 1"}, tmp_project)
        assert result["success"] is False
        assert result["exit_code"] == 1

    def test_timeout(self, tmp_project: Path):
        result = handle_bash({"command": "sleep 10", "timeout": 1}, tmp_project)
        assert result["success"] is False
        assert "timed out" in result.get("error", "").lower()


class TestExtractFrontmatter:
    def test_valid_frontmatter(self):
        content = "---\nname: Test\nvalue: 42\n---\n# Body\n"
        fm = _extract_frontmatter(content)
        assert fm["name"] == "Test"
        assert fm["value"] == 42

    def test_no_frontmatter(self):
        assert _extract_frontmatter("# Just content") == {}

    def test_empty_frontmatter(self):
        assert _extract_frontmatter("---\n---\n# Body") == {}
