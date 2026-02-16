"""Tests for session-to-vault design log export."""

from __future__ import annotations

from pathlib import Path

import pytest

from cadforge.core.session import Message, Session
from cadforge.core.session_vault import (
    _build_session_markdown,
    save_session_to_vault,
)


class TestBuildSessionMarkdown:
    def test_basic_markdown(self):
        md = _build_session_markdown(
            session_id="test-session",
            user_messages=["Make a 50mm cube"],
            assistant_messages=["Here is a cube with 50mm sides"],
            cadquery_snippets=[],
        )
        assert "test-session" in md
        assert "Make a 50mm cube" in md
        assert "---" in md  # Has frontmatter

    def test_includes_cadquery_code(self):
        md = _build_session_markdown(
            session_id="test-cad",
            user_messages=["Make a box"],
            assistant_messages=["Generated a box"],
            cadquery_snippets=[{"name": "box", "code": "result = cq.Workplane().box(10, 10, 10)"}],
        )
        assert "```python" in md
        assert "cq.Workplane().box(10, 10, 10)" in md
        assert "Generated CadQuery Code" in md

    def test_tags_include_cadquery(self):
        md = _build_session_markdown(
            session_id="test-tags",
            user_messages=["Make a thing"],
            assistant_messages=[],
            cadquery_snippets=[{"name": "thing", "code": "x = 1"}],
        )
        assert "cadquery" in md
        assert "session" in md

    def test_empty_messages(self):
        md = _build_session_markdown(
            session_id="test-empty",
            user_messages=[],
            assistant_messages=[],
            cadquery_snippets=[],
        )
        assert "Design Session" in md

    def test_truncates_long_messages(self):
        long_msg = "x" * 500
        md = _build_session_markdown(
            session_id="test-trunc",
            user_messages=[long_msg],
            assistant_messages=[],
            cadquery_snippets=[],
        )
        assert "..." in md
        # Should be truncated, not full 500 chars in user section
        assert "x" * 400 not in md


class TestSaveSessionToVault:
    def test_saves_basic_session(self, tmp_project: Path):
        messages = [
            Message(role="user", content="Design a bracket"),
            Message(role="assistant", content="I'll create a bracket for you."),
        ]
        path = save_session_to_vault(tmp_project, "test-save", messages)
        assert path is not None
        assert path.exists()
        content = path.read_text()
        assert "bracket" in content.lower()
        assert "test-save" in content

    def test_returns_none_for_empty_session(self, tmp_project: Path):
        result = save_session_to_vault(tmp_project, "empty", [])
        assert result is None

    def test_returns_none_for_single_message(self, tmp_project: Path):
        messages = [Message(role="user", content="hi")]
        result = save_session_to_vault(tmp_project, "short", messages)
        assert result is None

    def test_saves_to_vault_sessions_dir(self, tmp_project: Path):
        messages = [
            Message(role="user", content="Make a gear"),
            Message(role="assistant", content="Here's a gear design."),
        ]
        path = save_session_to_vault(tmp_project, "test-vault-dir", messages)
        assert path is not None
        assert "vault" in str(path)
        assert "sessions" in str(path)

    def test_extracts_cadquery_from_tool_use(self, tmp_project: Path):
        messages = [
            Message(role="user", content="Make a cube"),
            Message(
                role="assistant",
                content=[
                    {"type": "text", "text": "Here's a cube:"},
                    {
                        "type": "tool_use",
                        "id": "tu_1",
                        "name": "ExecuteCadQuery",
                        "input": {
                            "code": "result = cq.Workplane().box(50, 50, 50)",
                            "output_name": "cube",
                        },
                    },
                ],
            ),
        ]
        path = save_session_to_vault(tmp_project, "test-cq", messages)
        assert path is not None
        content = path.read_text()
        assert "cq.Workplane().box(50, 50, 50)" in content
        assert "cadquery" in content

    def test_skips_tool_result_messages(self, tmp_project: Path):
        messages = [
            Message(role="user", content="Make something"),
            Message(role="assistant", content="Working on it."),
            Message(role="user", content='[{"type":"tool_result","content":"ok"}]'),
            Message(role="assistant", content="Done!"),
        ]
        path = save_session_to_vault(tmp_project, "test-skip", messages)
        assert path is not None
        content = path.read_text()
        # Tool result JSON should not appear in user requests
        assert "tool_result" not in content

    def test_frontmatter_format(self, tmp_project: Path):
        messages = [
            Message(role="user", content="Test frontmatter"),
            Message(role="assistant", content="Response"),
        ]
        path = save_session_to_vault(tmp_project, "test-fm", messages)
        content = path.read_text()
        lines = content.split("\n")
        assert lines[0] == "---"
        # Find closing ---
        closing_idx = None
        for i, line in enumerate(lines[1:], 1):
            if line == "---":
                closing_idx = i
                break
        assert closing_idx is not None
        assert "session_id:" in content
        assert "tags:" in content
