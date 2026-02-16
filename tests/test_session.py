"""Tests for CadForge session persistence and context management."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from cadforge.core.session import (
    Message,
    Session,
    SessionIndex,
    SessionMetadata,
)
from cadforge.core.context import (
    ContextState,
    compact_messages,
    estimate_message_tokens,
    estimate_messages_tokens,
    estimate_tokens,
    build_summary_prompt,
)


class TestMessage:
    def test_to_dict(self):
        msg = Message(role="user", content="hello", timestamp=1000.0)
        d = msg.to_dict()
        assert d["role"] == "user"
        assert d["content"] == "hello"
        assert d["timestamp"] == 1000.0

    def test_from_dict(self):
        d = {"role": "assistant", "content": "hi", "timestamp": 2000.0}
        msg = Message.from_dict(d)
        assert msg.role == "assistant"
        assert msg.content == "hi"

    def test_roundtrip(self):
        msg = Message(role="user", content="test", tool_use_id="abc")
        d = msg.to_dict()
        msg2 = Message.from_dict(d)
        assert msg2.role == msg.role
        assert msg2.content == msg.content
        assert msg2.tool_use_id == msg.tool_use_id

    def test_optional_fields_excluded(self):
        msg = Message(role="user", content="test")
        d = msg.to_dict()
        assert "tool_use_id" not in d
        assert "tool_result" not in d
        assert "usage" not in d


class TestSession:
    def test_create_session(self, tmp_project: Path):
        session = Session(tmp_project, "test-session")
        assert session.session_id == "test-session"
        assert session.message_count == 0

    def test_add_and_persist(self, tmp_project: Path):
        session = Session(tmp_project, "test-persist")
        session.add_user_message("hello")
        session.add_assistant_message("hi there")
        assert session.message_count == 2
        assert session.file_path.exists()

    def test_load_session(self, tmp_project: Path):
        # Write
        s1 = Session(tmp_project, "test-load")
        s1.add_user_message("first message")
        s1.add_assistant_message("response")

        # Load in new instance
        s2 = Session(tmp_project, "test-load")
        s2.load()
        assert s2.message_count == 2
        assert s2.messages[0].content == "first message"
        assert s2.messages[1].content == "response"

    def test_load_nonexistent(self, tmp_project: Path):
        s = Session(tmp_project, "nonexistent")
        s.load()
        assert s.message_count == 0

    def test_get_api_messages(self, tmp_project: Path):
        s = Session(tmp_project, "test-api")
        s.add_user_message("hello")
        s.add_assistant_message("hi")
        msgs = s.get_api_messages()
        assert len(msgs) == 2
        assert msgs[0] == {"role": "user", "content": "hello"}
        assert msgs[1] == {"role": "assistant", "content": "hi"}

    def test_summary(self, tmp_project: Path):
        s = Session(tmp_project, "test-summary")
        s.add_user_message("Make a gear with 20 teeth")
        assert "gear" in s.summary.lower()

    def test_summary_truncates(self, tmp_project: Path):
        s = Session(tmp_project, "test-trunc")
        s.add_user_message("x" * 200)
        assert len(s.summary) < 120

    def test_summary_empty(self, tmp_project: Path):
        s = Session(tmp_project, "test-empty")
        assert "empty" in s.summary.lower()

    def test_to_metadata(self, tmp_project: Path):
        s = Session(tmp_project, "test-meta")
        s.add_user_message("hello")
        meta = s.to_metadata()
        assert meta.session_id == "test-meta"
        assert meta.message_count == 1

    def test_auto_generate_id(self, tmp_project: Path):
        s = Session(tmp_project)
        assert s.session_id.startswith("session-")


class TestSessionIndex:
    def test_update_and_list(self, tmp_project: Path):
        index = SessionIndex(tmp_project)
        session = Session(tmp_project, "s1")
        session.add_user_message("test")
        index.update(session)

        sessions = index.list_sessions()
        assert len(sessions) == 1
        assert sessions[0].session_id == "s1"

    def test_multiple_sessions(self, tmp_project: Path):
        index = SessionIndex(tmp_project)
        for i in range(3):
            s = Session(tmp_project, f"s{i}")
            s.add_user_message(f"msg {i}")
            index.update(s)

        sessions = index.list_sessions()
        assert len(sessions) == 3

    def test_get_latest(self, tmp_project: Path):
        index = SessionIndex(tmp_project)
        s1 = Session(tmp_project, "s1")
        s1.add_user_message("old")
        index.update(s1)

        s2 = Session(tmp_project, "s2")
        s2.add_user_message("new")
        index.update(s2)

        latest = index.get_latest()
        assert latest is not None
        assert latest.session_id == "s2"

    def test_get_by_id(self, tmp_project: Path):
        index = SessionIndex(tmp_project)
        s = Session(tmp_project, "find-me")
        s.add_user_message("hello")
        index.update(s)

        found = index.get_by_id("find-me")
        assert found is not None
        assert found.session_id == "find-me"

    def test_get_by_id_missing(self, tmp_project: Path):
        index = SessionIndex(tmp_project)
        assert index.get_by_id("nonexistent") is None

    def test_update_existing(self, tmp_project: Path):
        index = SessionIndex(tmp_project)
        s = Session(tmp_project, "s1")
        s.add_user_message("first")
        index.update(s)

        s.add_user_message("second")
        index.update(s)

        sessions = index.list_sessions()
        assert len(sessions) == 1
        assert sessions[0].message_count == 2

    def test_empty_index(self, tmp_project: Path):
        index = SessionIndex(tmp_project)
        assert index.list_sessions() == []
        assert index.get_latest() is None


class TestEstimateTokens:
    def test_basic_estimation(self):
        assert estimate_tokens("hello world") > 0

    def test_empty_string(self):
        assert estimate_tokens("") == 1  # minimum 1

    def test_proportional(self):
        short = estimate_tokens("hi")
        long = estimate_tokens("a" * 1000)
        assert long > short


class TestEstimateMessageTokens:
    def test_string_content(self):
        msg = {"role": "user", "content": "hello world"}
        assert estimate_message_tokens(msg) > 0

    def test_list_content(self):
        msg = {"role": "assistant", "content": [{"type": "text", "text": "hello"}]}
        assert estimate_message_tokens(msg) > 0

    def test_empty_content(self):
        msg = {"role": "user", "content": ""}
        assert estimate_message_tokens(msg) >= 0


class TestEstimateMessagesTokens:
    def test_multiple_messages(self):
        msgs = [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "world"},
        ]
        assert estimate_messages_tokens(msgs) > 0


class TestContextState:
    def test_usage_ratio(self):
        state = ContextState(estimated_tokens=80000, context_window=100000)
        assert state.usage_ratio == 0.8

    def test_needs_compaction(self):
        state = ContextState(estimated_tokens=85000, context_window=100000)
        assert state.needs_compaction is True

    def test_no_compaction_needed(self):
        state = ContextState(estimated_tokens=50000, context_window=100000)
        assert state.needs_compaction is False

    def test_remaining_tokens(self):
        state = ContextState(estimated_tokens=60000, context_window=100000)
        assert state.remaining_tokens == 40000


class TestCompactMessages:
    def test_compact_replaces_old(self):
        messages = [
            {"role": "user", "content": f"msg {i}"}
            for i in range(10)
        ]
        result = compact_messages(messages, "Summary of msgs 0-5", keep_recent=4)
        assert len(result) == 5  # summary + 4 recent
        assert "summary" in result[0]["content"].lower()

    def test_no_compact_when_few(self):
        messages = [
            {"role": "user", "content": "msg 1"},
            {"role": "assistant", "content": "msg 2"},
        ]
        result = compact_messages(messages, "summary", keep_recent=4)
        assert len(result) == 2

    def test_preserves_recent(self):
        messages = [
            {"role": "user", "content": f"msg {i}"}
            for i in range(10)
        ]
        result = compact_messages(messages, "summary", keep_recent=3)
        assert result[-1]["content"] == "msg 9"
        assert result[-2]["content"] == "msg 8"
        assert result[-3]["content"] == "msg 7"


class TestBuildSummaryPrompt:
    def test_includes_messages(self):
        messages = [
            {"role": "user", "content": "Make a cube"},
            {"role": "assistant", "content": "Here is a cube"},
        ]
        prompt = build_summary_prompt(messages)
        assert "cube" in prompt.lower()
        assert "Summarize" in prompt
