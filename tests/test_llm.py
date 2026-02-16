"""Tests for LLM provider abstraction."""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from cadforge.config import CadForgeSettings
from cadforge.core.events import AgentEvent, EventType
from cadforge.core.llm import (
    AnthropicProvider,
    AsyncAnthropicProvider,
    OllamaProvider,
    create_provider,
)


class TestCreateProvider:
    def test_defaults_to_anthropic(self):
        settings = CadForgeSettings()
        provider = create_provider(settings)
        assert isinstance(provider, AnthropicProvider)

    def test_anthropic_explicit(self):
        settings = CadForgeSettings(provider="anthropic")
        provider = create_provider(settings)
        assert isinstance(provider, AnthropicProvider)

    def test_ollama_provider(self):
        settings = CadForgeSettings(provider="ollama", model="qwen2.5-coder:14b")
        provider = create_provider(settings)
        assert isinstance(provider, OllamaProvider)

    def test_ollama_with_base_url(self):
        settings = CadForgeSettings(
            provider="ollama",
            base_url="http://myhost:11434/v1",
        )
        provider = create_provider(settings)
        assert isinstance(provider, OllamaProvider)
        assert provider._base_url == "http://myhost:11434/v1"

    def test_ollama_default_base_url(self):
        settings = CadForgeSettings(provider="ollama")
        provider = create_provider(settings)
        assert provider._base_url == "http://localhost:11434/v1"

    def test_anthropic_receives_auth_creds(self):
        settings = CadForgeSettings(provider="anthropic")
        mock_creds = MagicMock()
        provider = create_provider(settings, auth_creds=mock_creds)
        assert isinstance(provider, AnthropicProvider)
        assert provider._auth_creds is mock_creds


class TestOllamaTranslateTools:
    def test_basic_tool_translation(self):
        anthropic_tools = [
            {
                "name": "ReadFile",
                "description": "Read a file",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "File path"},
                    },
                    "required": ["path"],
                },
            }
        ]
        oai_tools = OllamaProvider._translate_tools(anthropic_tools)
        assert len(oai_tools) == 1
        tool = oai_tools[0]
        assert tool["type"] == "function"
        assert tool["function"]["name"] == "ReadFile"
        assert tool["function"]["description"] == "Read a file"
        assert tool["function"]["parameters"]["type"] == "object"
        assert "path" in tool["function"]["parameters"]["properties"]

    def test_multiple_tools(self):
        tools = [
            {"name": "A", "description": "Tool A", "input_schema": {"type": "object"}},
            {"name": "B", "description": "Tool B", "input_schema": {"type": "object"}},
        ]
        oai_tools = OllamaProvider._translate_tools(tools)
        assert len(oai_tools) == 2
        assert oai_tools[0]["function"]["name"] == "A"
        assert oai_tools[1]["function"]["name"] == "B"

    def test_missing_description(self):
        tools = [{"name": "X", "input_schema": {"type": "object"}}]
        oai_tools = OllamaProvider._translate_tools(tools)
        assert oai_tools[0]["function"]["description"] == ""


class TestOllamaTranslateMessages:
    def test_simple_string_messages(self):
        messages = [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi there"},
        ]
        result = OllamaProvider._translate_messages(messages)
        assert len(result) == 2
        assert result[0] == {"role": "user", "content": "hello"}
        assert result[1] == {"role": "assistant", "content": "hi there"}

    def test_assistant_with_tool_use(self):
        messages = [
            {
                "role": "assistant",
                "content": [
                    {"type": "text", "text": "Let me read that file."},
                    {
                        "type": "tool_use",
                        "id": "call_123",
                        "name": "ReadFile",
                        "input": {"path": "test.py"},
                    },
                ],
            }
        ]
        result = OllamaProvider._translate_messages(messages)
        assert len(result) == 1
        msg = result[0]
        assert msg["role"] == "assistant"
        assert msg["content"] == "Let me read that file."
        assert len(msg["tool_calls"]) == 1
        tc = msg["tool_calls"][0]
        assert tc["id"] == "call_123"
        assert tc["type"] == "function"
        assert tc["function"]["name"] == "ReadFile"
        assert json.loads(tc["function"]["arguments"]) == {"path": "test.py"}

    def test_user_with_tool_results(self):
        messages = [
            {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "call_123",
                        "content": '{"text": "file contents"}',
                    },
                ],
            }
        ]
        result = OllamaProvider._translate_messages(messages)
        assert len(result) == 1
        msg = result[0]
        assert msg["role"] == "tool"
        assert msg["tool_call_id"] == "call_123"
        assert msg["content"] == '{"text": "file contents"}'

    def test_multiple_tool_results(self):
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "tool_result", "tool_use_id": "c1", "content": "r1"},
                    {"type": "tool_result", "tool_use_id": "c2", "content": "r2"},
                ],
            }
        ]
        result = OllamaProvider._translate_messages(messages)
        assert len(result) == 2
        assert result[0]["tool_call_id"] == "c1"
        assert result[1]["tool_call_id"] == "c2"

    def test_user_text_content_blocks(self):
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Hello"},
                    {"type": "text", "text": "World"},
                ],
            }
        ]
        result = OllamaProvider._translate_messages(messages)
        assert len(result) == 1
        assert result[0]["content"] == "Hello\nWorld"


class TestOllamaNormalizeResponse:
    def _make_response(self, content=None, tool_calls=None, prompt_tokens=10, completion_tokens=5):
        """Build a mock OpenAI ChatCompletion response."""
        message = SimpleNamespace(content=content, tool_calls=tool_calls)
        choice = SimpleNamespace(message=message)
        usage = SimpleNamespace(prompt_tokens=prompt_tokens, completion_tokens=completion_tokens)
        return SimpleNamespace(choices=[choice], usage=usage)

    def test_text_only_response(self):
        resp = self._make_response(content="Hello!")
        result = OllamaProvider._normalize_response(resp)
        assert len(result["content"]) == 1
        assert result["content"][0] == {"type": "text", "text": "Hello!"}
        assert result["usage"] == {"input_tokens": 10, "output_tokens": 5}

    def test_tool_call_response(self):
        tc = SimpleNamespace(
            id="call_abc",
            function=SimpleNamespace(name="ReadFile", arguments='{"path": "x.py"}'),
        )
        resp = self._make_response(content="Reading file.", tool_calls=[tc])
        result = OllamaProvider._normalize_response(resp)
        assert len(result["content"]) == 2
        assert result["content"][0] == {"type": "text", "text": "Reading file."}
        assert result["content"][1]["type"] == "tool_use"
        assert result["content"][1]["name"] == "ReadFile"
        assert result["content"][1]["input"] == {"path": "x.py"}
        assert result["content"][1]["id"] == "call_abc"

    def test_tool_call_without_text(self):
        tc = SimpleNamespace(
            id="call_abc",
            function=SimpleNamespace(name="Bash", arguments='{"command": "ls"}'),
        )
        resp = self._make_response(content=None, tool_calls=[tc])
        result = OllamaProvider._normalize_response(resp)
        assert len(result["content"]) == 1
        assert result["content"][0]["type"] == "tool_use"

    def test_empty_response(self):
        resp = SimpleNamespace(choices=[], usage=None)
        result = OllamaProvider._normalize_response(resp)
        assert result["content"][0]["text"] == "No response from model"

    def test_invalid_json_arguments(self):
        tc = SimpleNamespace(
            id="call_x",
            function=SimpleNamespace(name="ReadFile", arguments="not json"),
        )
        resp = self._make_response(content=None, tool_calls=[tc])
        result = OllamaProvider._normalize_response(resp)
        assert result["content"][0]["input"] == {}

    def test_no_tool_call_id_generates_one(self):
        tc = SimpleNamespace(
            id=None,
            function=SimpleNamespace(name="ReadFile", arguments="{}"),
        )
        resp = self._make_response(content=None, tool_calls=[tc])
        result = OllamaProvider._normalize_response(resp)
        assert result["content"][0]["id"].startswith("call_")


class TestOllamaFormatToolResults:
    def test_format_single_result(self):
        provider = OllamaProvider()
        results = [
            {"type": "tool_result", "tool_use_id": "c1", "content": "output"},
        ]
        formatted = provider.format_tool_results(results)
        assert len(formatted) == 1
        assert formatted[0]["role"] == "tool"
        assert formatted[0]["tool_call_id"] == "c1"
        assert formatted[0]["content"] == "output"

    def test_format_multiple_results(self):
        provider = OllamaProvider()
        results = [
            {"type": "tool_result", "tool_use_id": "c1", "content": "out1"},
            {"type": "tool_result", "tool_use_id": "c2", "content": "out2"},
        ]
        formatted = provider.format_tool_results(results)
        assert len(formatted) == 2


class TestAnthropicFormatToolResults:
    def test_passthrough(self):
        provider = AnthropicProvider()
        results = [
            {"type": "tool_result", "tool_use_id": "c1", "content": "output"},
        ]
        formatted = provider.format_tool_results(results)
        assert formatted is results  # Same reference — no transformation


class TestOllamaProviderCall:
    def test_call_with_mocked_client(self):
        provider = OllamaProvider()

        tc = SimpleNamespace(
            id="call_1",
            function=SimpleNamespace(name="ReadFile", arguments='{"path": "a.py"}'),
        )
        message = SimpleNamespace(content="I'll read that.", tool_calls=[tc])
        choice = SimpleNamespace(message=message)
        usage = SimpleNamespace(prompt_tokens=100, completion_tokens=50)
        mock_response = SimpleNamespace(choices=[choice], usage=usage)

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response
        provider._client = mock_client

        settings = CadForgeSettings(provider="ollama", model="qwen2.5-coder:14b")
        result = provider.call(
            messages=[{"role": "user", "content": "Read a.py"}],
            system_prompt="You are CadForge.",
            tools=[{"name": "ReadFile", "description": "Read", "input_schema": {"type": "object"}}],
            settings=settings,
        )

        assert result["content"][0] == {"type": "text", "text": "I'll read that."}
        assert result["content"][1]["type"] == "tool_use"
        assert result["content"][1]["name"] == "ReadFile"
        assert result["usage"] == {"input_tokens": 100, "output_tokens": 50}

        # Verify the call was made with correct args
        call_kwargs = mock_client.chat.completions.create.call_args[1]
        assert call_kwargs["model"] == "qwen2.5-coder:14b"
        assert call_kwargs["messages"][0] == {"role": "system", "content": "You are CadForge."}
        assert call_kwargs["messages"][1] == {"role": "user", "content": "Read a.py"}
        assert call_kwargs["tools"][0]["type"] == "function"

    def test_missing_openai_sdk(self):
        provider = OllamaProvider()
        provider._client = None  # Force re-import

        settings = CadForgeSettings(provider="ollama", model="test")
        with patch.dict("sys.modules", {"openai": None}):
            # The import will fail inside _get_client
            provider._client = None
            result = provider.call(
                messages=[],
                system_prompt="test",
                tools=[],
                settings=settings,
            )
            # Should get an error response, not crash
            assert len(result["content"]) == 1
            assert result["content"][0]["type"] == "text"


class TestAnthropicProviderCall:
    def test_missing_anthropic_sdk(self):
        provider = AnthropicProvider()
        settings = CadForgeSettings()

        with patch.dict("sys.modules", {"anthropic": None}):
            result = provider.call(
                messages=[],
                system_prompt="test",
                tools=[],
                settings=settings,
            )
            assert "not installed" in result["content"][0]["text"].lower() or "error" in result["content"][0]["text"].lower()


class TestAgentUpdateProvider:
    """Tests for Agent.update_provider() hot-swap."""

    def test_swap_to_ollama(self, tmp_path):
        """Verify update_provider creates OllamaProvider when settings say ollama."""
        from cadforge.core.agent import Agent
        from cadforge.core.auth import AuthCredentials

        # Set up minimal project structure
        (tmp_path / "CADFORGE.md").write_text("# Test\n")
        cadforge_dir = tmp_path / ".cadforge"
        cadforge_dir.mkdir()
        (cadforge_dir / "memory").mkdir()
        (cadforge_dir / "memory" / "MEMORY.md").write_text("")

        settings = CadForgeSettings(provider="anthropic")
        agent = Agent(
            project_root=tmp_path,
            settings=settings,
        )
        assert isinstance(agent._provider, AnthropicProvider)

        # Switch to ollama
        agent.settings.provider = "ollama"
        agent.settings.model = "qwen2.5-coder:14b"
        agent.settings.base_url = "http://localhost:11434/v1"
        agent.update_provider()

        assert isinstance(agent._provider, OllamaProvider)
        assert agent._auth_creds.source == "ollama"

    def test_swap_to_anthropic(self, tmp_path):
        """Verify update_provider creates AnthropicProvider when switching back."""
        from cadforge.core.agent import Agent
        from cadforge.core.auth import AuthCredentials

        (tmp_path / "CADFORGE.md").write_text("# Test\n")
        cadforge_dir = tmp_path / ".cadforge"
        cadforge_dir.mkdir()
        (cadforge_dir / "memory").mkdir()
        (cadforge_dir / "memory" / "MEMORY.md").write_text("")

        settings = CadForgeSettings(provider="ollama", model="test-model")
        agent = Agent(
            project_root=tmp_path,
            settings=settings,
        )
        assert isinstance(agent._provider, OllamaProvider)

        # Switch to anthropic
        agent.settings.provider = "anthropic"
        agent.settings.model = "claude-sonnet-4-5-20250929"
        agent.update_provider()

        assert isinstance(agent._provider, AnthropicProvider)


# ---------------------------------------------------------------------------
# Async retry tests for AsyncAnthropicProvider
# ---------------------------------------------------------------------------

anthropic = pytest.importorskip("anthropic", reason="anthropic SDK not installed")


class _FakeStreamContext:
    """Async context manager that yields events from a list, or raises."""

    def __init__(self, events=None, error=None):
        self._events = events or []
        self._error = error

    async def __aenter__(self):
        if self._error:
            raise self._error
        return self

    async def __aexit__(self, *args):
        pass

    def __aiter__(self):
        return self._iter_events()

    async def _iter_events(self):
        for ev in self._events:
            yield ev


def _make_stream_events():
    """Return a minimal set of streaming events for a successful response."""
    return [
        SimpleNamespace(type="message_start", message=SimpleNamespace(usage=SimpleNamespace(input_tokens=10))),
        SimpleNamespace(type="content_block_start", content_block=SimpleNamespace(type="text")),
        SimpleNamespace(type="content_block_delta", delta=SimpleNamespace(type="text_delta", text="Hello")),
        SimpleNamespace(type="content_block_stop"),
        SimpleNamespace(type="message_delta", usage=SimpleNamespace(output_tokens=5)),
    ]


class TestAsyncAnthropicRetry:
    """Tests for retry logic in AsyncAnthropicProvider.stream()."""

    def _make_provider_and_queue(self):
        return AsyncAnthropicProvider(), asyncio.Queue()

    def _patch_client(self, stream_side_effect):
        """Patch auth to return a mock client with given stream side_effect."""
        mock_client = MagicMock()
        mock_client.messages.stream = MagicMock(side_effect=stream_side_effect)

        def fake_create(creds=None):
            return mock_client, creds

        return patch(
            "cadforge.core.auth.create_async_anthropic_client",
            side_effect=fake_create,
        )

    def _drain_queue(self, queue):
        events = []
        while not queue.empty():
            events.append(queue.get_nowait())
        return events

    def test_retry_on_internal_server_error(self):
        """Should retry on 500 then succeed."""
        error_500 = anthropic.InternalServerError(
            message="Internal Server Error",
            response=MagicMock(status_code=500, headers={}),
            body=None,
        )

        call_count = 0

        def stream_side_effect(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _FakeStreamContext(error=error_500)
            return _FakeStreamContext(events=_make_stream_events())

        async def run():
            provider, eq = self._make_provider_and_queue()
            settings = CadForgeSettings()
            with self._patch_client(stream_side_effect):
                original_delays = AsyncAnthropicProvider._RETRY_DELAYS
                AsyncAnthropicProvider._RETRY_DELAYS = [0, 0, 0]
                try:
                    result = await provider.stream(
                        messages=[{"role": "user", "content": "hi"}],
                        system_prompt="test",
                        tools=[],
                        settings=settings,
                        event_queue=eq,
                    )
                finally:
                    AsyncAnthropicProvider._RETRY_DELAYS = original_delays
            return result, eq

        result, eq = asyncio.run(run())
        assert call_count == 2
        assert result["content"][0]["text"] == "Hello"

        events = self._drain_queue(eq)
        status_events = [e for e in events if e.type == EventType.STATUS]
        assert len(status_events) == 1
        assert "retrying (1/3)" in status_events[0].data["message"]

    def test_no_retry_on_auth_error(self):
        """Auth errors should not be retried."""
        auth_error = anthropic.AuthenticationError(
            message="Invalid api_key",
            response=MagicMock(status_code=401, headers={}),
            body=None,
        )

        call_count = 0

        def stream_side_effect(**kwargs):
            nonlocal call_count
            call_count += 1
            return _FakeStreamContext(error=auth_error)

        async def run():
            provider, eq = self._make_provider_and_queue()
            settings = CadForgeSettings()
            with self._patch_client(stream_side_effect):
                original_delays = AsyncAnthropicProvider._RETRY_DELAYS
                AsyncAnthropicProvider._RETRY_DELAYS = [0, 0, 0]
                try:
                    result = await provider.stream(
                        messages=[{"role": "user", "content": "hi"}],
                        system_prompt="test",
                        tools=[],
                        settings=settings,
                        event_queue=eq,
                    )
                finally:
                    AsyncAnthropicProvider._RETRY_DELAYS = original_delays
            return result

        result = asyncio.run(run())
        assert call_count == 1  # No retries
        assert "API error" in result["content"][0]["text"]

    def test_all_retries_exhausted(self):
        """When all retries fail, should return error response."""
        error_500 = anthropic.InternalServerError(
            message="Internal Server Error",
            response=MagicMock(status_code=500, headers={}),
            body=None,
        )

        call_count = 0

        def stream_side_effect(**kwargs):
            nonlocal call_count
            call_count += 1
            return _FakeStreamContext(error=error_500)

        async def run():
            provider, eq = self._make_provider_and_queue()
            settings = CadForgeSettings()
            with self._patch_client(stream_side_effect):
                original_delays = AsyncAnthropicProvider._RETRY_DELAYS
                AsyncAnthropicProvider._RETRY_DELAYS = [0, 0, 0]
                try:
                    result = await provider.stream(
                        messages=[{"role": "user", "content": "hi"}],
                        system_prompt="test",
                        tools=[],
                        settings=settings,
                        event_queue=eq,
                    )
                finally:
                    AsyncAnthropicProvider._RETRY_DELAYS = original_delays
            return result, eq

        result, eq = asyncio.run(run())
        # 1 initial + 3 retries = 4 attempts
        assert call_count == 4
        assert "API error" in result["content"][0]["text"]

        events = self._drain_queue(eq)
        status_events = [e for e in events if e.type == EventType.STATUS]
        assert len(status_events) == 3

    def test_text_done_pushed_before_error_when_mid_stream(self):
        """If error occurs after text deltas, text_done should precede the error event."""
        partial_events = [
            SimpleNamespace(type="message_start", message=SimpleNamespace(usage=SimpleNamespace(input_tokens=5))),
            SimpleNamespace(type="content_block_start", content_block=SimpleNamespace(type="text")),
            SimpleNamespace(type="content_block_delta", delta=SimpleNamespace(type="text_delta", text="Partial")),
        ]

        class _MidStreamErrorContext:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                pass

            def __aiter__(self):
                return self._iter()

            async def _iter(self):
                for ev in partial_events:
                    yield ev
                raise anthropic.InternalServerError(
                    message="Server error",
                    response=MagicMock(status_code=500, headers={}),
                    body=None,
                )

        call_count = 0

        def stream_side_effect(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _MidStreamErrorContext()
            return _FakeStreamContext(events=_make_stream_events())

        async def run():
            provider, eq = self._make_provider_and_queue()
            settings = CadForgeSettings()
            with self._patch_client(stream_side_effect):
                original_delays = AsyncAnthropicProvider._RETRY_DELAYS
                AsyncAnthropicProvider._RETRY_DELAYS = [0, 0, 0]
                try:
                    result = await provider.stream(
                        messages=[{"role": "user", "content": "hi"}],
                        system_prompt="test",
                        tools=[],
                        settings=settings,
                        event_queue=eq,
                    )
                finally:
                    AsyncAnthropicProvider._RETRY_DELAYS = original_delays
            return result, eq

        result, eq = asyncio.run(run())
        assert call_count == 2
        assert result["content"][0]["text"] == "Hello"

        events = self._drain_queue(eq)
        # Find the text_done with empty text (closing partial stream) and the status event
        text_done_indices = [i for i, e in enumerate(events) if e.type == EventType.TEXT_DONE and e.data.get("text", "") == ""]
        status_indices = [i for i, e in enumerate(events) if e.type == EventType.STATUS]
        # text_done (closing partial) should appear before the retry status
        assert text_done_indices and status_indices
        assert text_done_indices[0] < status_indices[0]
