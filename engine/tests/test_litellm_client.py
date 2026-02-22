"""Tests for LiteLLMSubagentClient."""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from cadforge_engine.agent.llm import (
    LiteLLMSubagentClient,
    create_subagent_client,
    _normalize_openai_response,
)


def _make_openai_response(content: str = "Hello", tool_calls=None, finish_reason="stop"):
    """Create a mock OpenAI-format completion response."""
    message = SimpleNamespace(
        content=content,
        tool_calls=tool_calls,
    )
    choice = SimpleNamespace(
        message=message,
        finish_reason=finish_reason,
    )
    usage = SimpleNamespace(
        prompt_tokens=10,
        completion_tokens=20,
    )
    return SimpleNamespace(choices=[choice], usage=usage)


def _make_tool_call(name: str = "ExecuteCadQuery", args: dict | None = None):
    """Create a mock tool call."""
    return SimpleNamespace(
        id="call_abc123",
        type="function",
        function=SimpleNamespace(
            name=name,
            arguments=json.dumps(args or {"code": "result = 1"}),
        ),
    )


class TestLiteLLMSubagentClient:
    def test_init_defaults(self):
        client = LiteLLMSubagentClient()
        assert client.model == "minimax/MiniMax-M2.5"
        assert client.max_tokens == 8192
        assert client._api_key is None

    def test_init_custom(self):
        client = LiteLLMSubagentClient(
            model="zai/glm-5",
            max_tokens=4096,
            api_key="test-key",
        )
        assert client.model == "zai/glm-5"
        assert client.max_tokens == 4096
        assert client._api_key == "test-key"

    def test_sync_call(self):
        mock_litellm = MagicMock()
        mock_litellm.completion.return_value = _make_openai_response("Test output")

        with patch.dict("sys.modules", {"litellm": mock_litellm}):
            client = LiteLLMSubagentClient(model="test/model")
            result = client.call(
                messages=[{"role": "user", "content": "Hello"}],
                system="You are a test",
                tools=[],
            )

        assert result["content"][0]["type"] == "text"
        assert result["content"][0]["text"] == "Test output"
        assert result["stop_reason"] == "stop"
        assert result["usage"]["input_tokens"] == 10
        assert result["usage"]["output_tokens"] == 20

        # Verify litellm.completion was called with correct args
        call_kwargs = mock_litellm.completion.call_args[1]
        assert call_kwargs["model"] == "test/model"
        assert call_kwargs["max_tokens"] == 8192
        assert len(call_kwargs["messages"]) == 2  # system + user

    def test_sync_call_with_tools(self):
        tc = _make_tool_call("ExecuteCadQuery", {"code": "result = 1"})
        mock_litellm = MagicMock()
        mock_litellm.completion.return_value = _make_openai_response(
            content=None, tool_calls=[tc], finish_reason="tool_calls",
        )

        with patch.dict("sys.modules", {"litellm": mock_litellm}):
            client = LiteLLMSubagentClient(model="test/model")
            tools = [{
                "name": "ExecuteCadQuery",
                "description": "Execute code",
                "input_schema": {"type": "object", "properties": {"code": {"type": "string"}}},
            }]
            result = client.call(
                messages=[{"role": "user", "content": "Generate code"}],
                system="You are a coder",
                tools=tools,
            )

        # Should have a tool_use block
        tool_blocks = [b for b in result["content"] if b["type"] == "tool_use"]
        assert len(tool_blocks) == 1
        assert tool_blocks[0]["name"] == "ExecuteCadQuery"
        assert tool_blocks[0]["input"] == {"code": "result = 1"}

        # Verify tools were translated
        call_kwargs = mock_litellm.completion.call_args[1]
        assert call_kwargs["tools"] is not None

    def test_sync_call_with_api_key(self):
        mock_litellm = MagicMock()
        mock_litellm.completion.return_value = _make_openai_response()

        with patch.dict("sys.modules", {"litellm": mock_litellm}):
            client = LiteLLMSubagentClient(model="test/model", api_key="my-secret")
            client.call(messages=[], system="test", tools=[])

        call_kwargs = mock_litellm.completion.call_args[1]
        assert call_kwargs["api_key"] == "my-secret"

    @pytest.mark.asyncio
    async def test_async_call(self):
        mock_litellm = MagicMock()
        mock_litellm.acompletion = AsyncMock(
            return_value=_make_openai_response("Async output")
        )

        with patch.dict("sys.modules", {"litellm": mock_litellm}):
            client = LiteLLMSubagentClient(model="test/model")
            result = await client.acall(
                messages=[{"role": "user", "content": "Hello"}],
                system="You are a test",
                tools=[],
            )

        assert result["content"][0]["text"] == "Async output"
        mock_litellm.acompletion.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_async_call_with_api_key(self):
        mock_litellm = MagicMock()
        mock_litellm.acompletion = AsyncMock(
            return_value=_make_openai_response()
        )

        with patch.dict("sys.modules", {"litellm": mock_litellm}):
            client = LiteLLMSubagentClient(model="test/model", api_key="async-key")
            await client.acall(messages=[], system="test", tools=[])

        call_kwargs = mock_litellm.acompletion.call_args[1]
        assert call_kwargs["api_key"] == "async-key"


class TestNormalizeOpenAIResponse:
    def test_text_response(self):
        resp = _make_openai_response("Hello world")
        result = _normalize_openai_response(resp)
        assert result["content"] == [{"type": "text", "text": "Hello world"}]

    def test_tool_call_response(self):
        tc = _make_tool_call("SearchVault", {"query": "test"})
        resp = _make_openai_response(content=None, tool_calls=[tc])
        result = _normalize_openai_response(resp)

        tool_blocks = [b for b in result["content"] if b["type"] == "tool_use"]
        assert len(tool_blocks) == 1
        assert tool_blocks[0]["name"] == "SearchVault"

    def test_empty_response(self):
        resp = SimpleNamespace(choices=[], usage=None)
        result = _normalize_openai_response(resp)
        assert result["content"][0]["text"] == "No response from model"


class TestFactory:
    def test_create_litellm_client(self):
        config = {"provider": "litellm", "api_key": "test"}
        client = create_subagent_client(config, model="minimax/MiniMax-M2.5")
        assert isinstance(client, LiteLLMSubagentClient)
        assert client.model == "minimax/MiniMax-M2.5"
        assert client._api_key == "test"

    def test_create_litellm_client_no_key(self):
        config = {"provider": "litellm"}
        client = create_subagent_client(config, model="zai/glm-5")
        assert isinstance(client, LiteLLMSubagentClient)
        assert client._api_key is None
