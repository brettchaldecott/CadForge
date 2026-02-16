"""LLM provider abstraction for CadForge.

Supports Anthropic (cloud) and Ollama (local) backends with a unified
response format so the agent loop doesn't need to know which provider
is in use.
"""

from __future__ import annotations

import json
import uuid
from typing import Any, Protocol

from cadforge.config import CadForgeSettings


class LLMProvider(Protocol):
    """Protocol for LLM providers."""

    def call(
        self,
        messages: list[dict[str, Any]],
        system_prompt: str,
        tools: list[dict[str, Any]],
        settings: CadForgeSettings,
    ) -> dict[str, Any]:
        """Call the LLM and return a normalized response.

        Returns:
            {
                "content": [
                    {"type": "text", "text": "..."},
                    {"type": "tool_use", "id": "...", "name": "...", "input": {...}},
                ],
                "usage": {"input_tokens": 0, "output_tokens": 0},
            }
        """
        ...

    def format_tool_results(
        self, tool_results: list[dict[str, Any]]
    ) -> list[dict[str, Any]] | dict[str, Any]:
        """Format tool results for the next API message.

        Takes Anthropic-style tool_result blocks and returns provider-specific format.
        For Anthropic: returns a single user message with content blocks.
        For Ollama/OpenAI: returns a list of tool messages.
        """
        ...


class AnthropicProvider:
    """Anthropic API provider using the anthropic SDK."""

    def __init__(self, auth_creds: Any = None):
        self._auth_creds = auth_creds

    def call(
        self,
        messages: list[dict[str, Any]],
        system_prompt: str,
        tools: list[dict[str, Any]],
        settings: CadForgeSettings,
    ) -> dict[str, Any]:
        try:
            from cadforge.core.auth import create_anthropic_client

            client, self._auth_creds = create_anthropic_client(self._auth_creds)
            response = client.messages.create(
                model=settings.model,
                max_tokens=settings.max_tokens,
                system=system_prompt,
                tools=tools,
                messages=messages,
            )
            return {
                "content": [
                    block.model_dump() if hasattr(block, "model_dump") else block
                    for block in response.content
                ],
                "usage": {
                    "input_tokens": response.usage.input_tokens,
                    "output_tokens": response.usage.output_tokens,
                },
            }
        except ImportError:
            return {
                "content": [
                    {
                        "type": "text",
                        "text": "Anthropic SDK not installed. Install with: pip install anthropic",
                    }
                ],
                "usage": {"input_tokens": 0, "output_tokens": 0},
            }
        except Exception as e:
            error_msg = str(e)
            if "api_key" in error_msg.lower() or "auth" in error_msg.lower():
                error_msg = (
                    f"Authentication error: {e}\n\n"
                    "CadForge supports three auth methods:\n"
                    "1. ANTHROPIC_API_KEY env var (API key billing)\n"
                    "2. ANTHROPIC_AUTH_TOKEN env var (OAuth token)\n"
                    "3. Automatic: Claude Code OAuth from macOS Keychain"
                )
            return {
                "content": [{"type": "text", "text": f"API error: {error_msg}"}],
                "usage": {"input_tokens": 0, "output_tokens": 0},
            }

    def format_tool_results(
        self, tool_results: list[dict[str, Any]]
    ) -> list[dict[str, Any]] | dict[str, Any]:
        """Anthropic uses tool_result content blocks in a user message."""
        return tool_results


class OllamaProvider:
    """Ollama provider using the OpenAI-compatible API.

    Ollama exposes an OpenAI-compatible endpoint at http://localhost:11434/v1.
    We use the openai Python SDK with a custom base_url.
    """

    DEFAULT_BASE_URL = "http://localhost:11434/v1"

    def __init__(self, base_url: str | None = None):
        self._base_url = base_url or self.DEFAULT_BASE_URL
        self._client = None

    def _get_client(self) -> Any:
        if self._client is None:
            from openai import OpenAI

            self._client = OpenAI(
                base_url=self._base_url,
                api_key="ollama",  # Required by SDK but ignored by Ollama
            )
        return self._client

    def call(
        self,
        messages: list[dict[str, Any]],
        system_prompt: str,
        tools: list[dict[str, Any]],
        settings: CadForgeSettings,
    ) -> dict[str, Any]:
        try:
            client = self._get_client()

            # Build OpenAI-style messages with system prompt as first message
            oai_messages = [{"role": "system", "content": system_prompt}]
            oai_messages.extend(self._translate_messages(messages))

            # Translate tool definitions from Anthropic to OpenAI format
            oai_tools = self._translate_tools(tools) if tools else None

            kwargs: dict[str, Any] = {
                "model": settings.model,
                "max_tokens": settings.max_tokens,
                "messages": oai_messages,
            }
            if oai_tools:
                kwargs["tools"] = oai_tools

            response = client.chat.completions.create(**kwargs)
            return self._normalize_response(response)

        except ImportError:
            return {
                "content": [
                    {
                        "type": "text",
                        "text": (
                            "OpenAI SDK not installed. "
                            "Install with: pip install 'cadforge[ollama]'"
                        ),
                    }
                ],
                "usage": {"input_tokens": 0, "output_tokens": 0},
            }
        except Exception as e:
            return {
                "content": [{"type": "text", "text": f"Ollama error: {e}"}],
                "usage": {"input_tokens": 0, "output_tokens": 0},
            }

    def format_tool_results(
        self, tool_results: list[dict[str, Any]]
    ) -> list[dict[str, Any]] | dict[str, Any]:
        """Convert Anthropic-style tool_result blocks to OpenAI-style tool messages."""
        oai_messages = []
        for result in tool_results:
            oai_messages.append({
                "role": "tool",
                "tool_call_id": result["tool_use_id"],
                "content": result.get("content", ""),
            })
        return oai_messages

    @staticmethod
    def _translate_tools(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Translate Anthropic tool definitions to OpenAI function format.

        Anthropic: {"name": ..., "description": ..., "input_schema": {...}}
        OpenAI:    {"type": "function", "function": {"name": ..., "description": ..., "parameters": {...}}}
        """
        oai_tools = []
        for tool in tools:
            oai_tools.append({
                "type": "function",
                "function": {
                    "name": tool["name"],
                    "description": tool.get("description", ""),
                    "parameters": tool.get("input_schema", {}),
                },
            })
        return oai_tools

    @staticmethod
    def _translate_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Translate Anthropic-style messages to OpenAI format.

        Handles:
        - Simple string content (pass through)
        - Content blocks with tool_use (assistant with tool_calls)
        - Content blocks with tool_result (tool messages)
        """
        oai_messages = []
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content")

            if isinstance(content, str):
                oai_messages.append({"role": role, "content": content})
                continue

            if not isinstance(content, list):
                oai_messages.append({"role": role, "content": str(content)})
                continue

            # Content is a list of blocks
            if role == "assistant":
                # Check for tool_use blocks
                text_parts = []
                tool_calls = []
                for block in content:
                    if block.get("type") == "text":
                        text_parts.append(block["text"])
                    elif block.get("type") == "tool_use":
                        tool_calls.append({
                            "id": block["id"],
                            "type": "function",
                            "function": {
                                "name": block["name"],
                                "arguments": json.dumps(block.get("input", {})),
                            },
                        })

                assistant_msg: dict[str, Any] = {
                    "role": "assistant",
                    "content": "\n".join(text_parts) if text_parts else None,
                }
                if tool_calls:
                    assistant_msg["tool_calls"] = tool_calls
                oai_messages.append(assistant_msg)

            elif role == "user":
                # Check for tool_result blocks
                tool_results = [
                    b for b in content if b.get("type") == "tool_result"
                ]
                if tool_results:
                    for result in tool_results:
                        oai_messages.append({
                            "role": "tool",
                            "tool_call_id": result["tool_use_id"],
                            "content": result.get("content", ""),
                        })
                else:
                    # Regular user content blocks
                    text = "\n".join(
                        b.get("text", "") for b in content if b.get("type") == "text"
                    )
                    oai_messages.append({"role": "user", "content": text})
            else:
                oai_messages.append({"role": role, "content": str(content)})

        return oai_messages

    @staticmethod
    def _normalize_response(response: Any) -> dict[str, Any]:
        """Normalize an OpenAI ChatCompletion response to Anthropic format."""
        choice = response.choices[0] if response.choices else None
        if choice is None:
            return {
                "content": [{"type": "text", "text": "No response from model"}],
                "usage": {"input_tokens": 0, "output_tokens": 0},
            }

        message = choice.message
        content_blocks: list[dict[str, Any]] = []

        # Add text content
        if message.content:
            content_blocks.append({"type": "text", "text": message.content})

        # Add tool calls as tool_use blocks
        if message.tool_calls:
            for tc in message.tool_calls:
                try:
                    args = json.loads(tc.function.arguments)
                except (json.JSONDecodeError, TypeError):
                    args = {}
                content_blocks.append({
                    "type": "tool_use",
                    "id": tc.id or f"call_{uuid.uuid4().hex[:24]}",
                    "name": tc.function.name,
                    "input": args,
                })

        if not content_blocks:
            content_blocks.append({"type": "text", "text": ""})

        usage = response.usage
        return {
            "content": content_blocks,
            "usage": {
                "input_tokens": usage.prompt_tokens if usage else 0,
                "output_tokens": usage.completion_tokens if usage else 0,
            },
        }


def create_provider(settings: CadForgeSettings, auth_creds: Any = None) -> LLMProvider:
    """Factory function to create the appropriate LLM provider."""
    if settings.provider == "ollama":
        return OllamaProvider(base_url=settings.base_url)
    return AnthropicProvider(auth_creds=auth_creds)


# ---------------------------------------------------------------------------
# Async streaming providers
# ---------------------------------------------------------------------------

import asyncio
from cadforge.core.events import AgentEvent


class AsyncAnthropicProvider:
    """Async Anthropic provider with streaming support.

    Uses the anthropic SDK's async streaming API, pushing AgentEvents
    to a queue as tokens arrive.
    """

    def __init__(self, auth_creds: Any = None):
        self._auth_creds = auth_creds

    # Transient error types that warrant automatic retry
    _RETRY_DELAYS = [1, 2, 4]  # seconds between retries

    async def stream(
        self,
        messages: list[dict[str, Any]],
        system_prompt: str,
        tools: list[dict[str, Any]],
        settings: CadForgeSettings,
        event_queue: asyncio.Queue[AgentEvent],
    ) -> dict[str, Any]:
        """Stream an LLM response, pushing events to the queue.

        Returns the same normalized response dict as the sync call().
        Automatically retries on transient API errors (500, 429, 529, network).
        """
        try:
            import anthropic as _anthropic

            _retryable = (
                _anthropic.InternalServerError,   # 500
                _anthropic.RateLimitError,         # 429
                _anthropic.APIConnectionError,     # network issues
            )
            _APIStatusError = _anthropic.APIStatusError
        except ImportError:
            _retryable = ()
            _APIStatusError = None

        try:
            from cadforge.core.auth import create_async_anthropic_client

            client, self._auth_creds = create_async_anthropic_client(self._auth_creds)
        except ImportError:
            error_resp = {
                "content": [
                    {
                        "type": "text",
                        "text": "Anthropic SDK not installed. Install with: pip install anthropic",
                    }
                ],
                "usage": {"input_tokens": 0, "output_tokens": 0},
            }
            await event_queue.put(AgentEvent.error(error_resp["content"][0]["text"]))
            return error_resp

        last_error: Exception | None = None
        was_streaming_text = False

        for attempt in range(len(self._RETRY_DELAYS) + 1):
            try:
                content_blocks: list[dict[str, Any]] = []
                usage_info: dict[str, int] = {"input_tokens": 0, "output_tokens": 0}

                # Accumulators for the current content block
                current_text = ""
                current_tool: dict[str, Any] | None = None
                current_tool_json = ""
                was_streaming_text = False

                async with client.messages.stream(
                    model=settings.model,
                    max_tokens=settings.max_tokens,
                    system=system_prompt,
                    tools=tools or [],
                    messages=messages,
                ) as stream:
                    async for event in stream:
                        etype = event.type

                        if etype == "message_start":
                            msg = getattr(event, "message", None)
                            if msg and hasattr(msg, "usage"):
                                usage_info["input_tokens"] = getattr(msg.usage, "input_tokens", 0)

                        elif etype == "message_delta":
                            delta_usage = getattr(event, "usage", None)
                            if delta_usage:
                                usage_info["output_tokens"] = getattr(
                                    delta_usage, "output_tokens", 0
                                )

                        elif etype == "content_block_start":
                            cb = getattr(event, "content_block", None)
                            if cb:
                                block_type = getattr(cb, "type", "text")
                                if block_type == "text":
                                    current_text = ""
                                elif block_type == "tool_use":
                                    current_tool = {
                                        "type": "tool_use",
                                        "id": getattr(cb, "id", ""),
                                        "name": getattr(cb, "name", ""),
                                        "input": {},
                                    }
                                    current_tool_json = ""
                                    await event_queue.put(
                                        AgentEvent.tool_use_start(
                                            current_tool["name"], current_tool["id"]
                                        )
                                    )

                        elif etype == "content_block_delta":
                            delta = getattr(event, "delta", None)
                            if delta:
                                delta_type = getattr(delta, "type", "")
                                if delta_type == "text_delta":
                                    text = getattr(delta, "text", "")
                                    current_text += text
                                    was_streaming_text = True
                                    await event_queue.put(AgentEvent.text_delta(text))
                                elif delta_type == "input_json_delta":
                                    partial = getattr(delta, "partial_json", "")
                                    current_tool_json += partial

                        elif etype == "content_block_stop":
                            if current_tool is not None:
                                # Finalize tool_use block
                                try:
                                    current_tool["input"] = json.loads(current_tool_json) if current_tool_json else {}
                                except json.JSONDecodeError:
                                    current_tool["input"] = {}
                                content_blocks.append(current_tool)
                                current_tool = None
                                current_tool_json = ""
                            else:
                                # Finalize text block
                                if current_text:
                                    content_blocks.append({"type": "text", "text": current_text})
                                    await event_queue.put(AgentEvent.text_done(current_text))
                                    was_streaming_text = False
                                current_text = ""

                if not content_blocks:
                    content_blocks.append({"type": "text", "text": ""})

                return {"content": content_blocks, "usage": usage_info}

            except Exception as e:
                last_error = e

                # Only retry transient errors (500, 429, 529, network)
                is_retryable = _retryable and isinstance(e, _retryable)
                if not is_retryable:
                    # Also retry 529 Overloaded via status_code
                    if _APIStatusError and isinstance(e, _APIStatusError):
                        is_retryable = getattr(e, "status_code", 0) == 529
                if not is_retryable:
                    break

                if attempt < len(self._RETRY_DELAYS):
                    delay = self._RETRY_DELAYS[attempt]
                    # Close the partial text line before status message
                    if was_streaming_text:
                        await event_queue.put(AgentEvent.text_done())
                        was_streaming_text = False
                    await event_queue.put(
                        AgentEvent.status(
                            f"API error, retrying ({attempt + 1}/{len(self._RETRY_DELAYS)})..."
                        )
                    )
                    await asyncio.sleep(delay)
                # else: fall through to error handling below

        # All retries exhausted or non-retryable error
        error_msg = str(last_error)
        if "api_key" in error_msg.lower() or "auth" in error_msg.lower():
            error_msg = (
                f"Authentication error: {last_error}\n\n"
                "CadForge supports three auth methods:\n"
                "1. ANTHROPIC_API_KEY env var (API key billing)\n"
                "2. ANTHROPIC_AUTH_TOKEN env var (OAuth token)\n"
                "3. Automatic: Claude Code OAuth from macOS Keychain"
            )
        # Ensure error renders on its own line if we were mid-stream
        if was_streaming_text:
            await event_queue.put(AgentEvent.text_done())
        error_resp = {
            "content": [{"type": "text", "text": f"API error: {error_msg}"}],
            "usage": {"input_tokens": 0, "output_tokens": 0},
        }
        await event_queue.put(AgentEvent.error(f"API error: {error_msg}"))
        return error_resp

    def format_tool_results(
        self, tool_results: list[dict[str, Any]]
    ) -> list[dict[str, Any]] | dict[str, Any]:
        return tool_results


class AsyncOllamaProvider:
    """Async Ollama provider with streaming support.

    Uses the openai SDK's async streaming API via Ollama's
    OpenAI-compatible endpoint.
    """

    DEFAULT_BASE_URL = "http://localhost:11434/v1"

    def __init__(self, base_url: str | None = None):
        self._base_url = base_url or self.DEFAULT_BASE_URL
        self._client = None

    def _get_client(self) -> Any:
        if self._client is None:
            from openai import AsyncOpenAI

            self._client = AsyncOpenAI(
                base_url=self._base_url,
                api_key="ollama",
            )
        return self._client

    async def stream(
        self,
        messages: list[dict[str, Any]],
        system_prompt: str,
        tools: list[dict[str, Any]],
        settings: CadForgeSettings,
        event_queue: asyncio.Queue[AgentEvent],
    ) -> dict[str, Any]:
        """Stream an LLM response, pushing events to the queue."""
        try:
            client = self._get_client()

            oai_messages = [{"role": "system", "content": system_prompt}]
            oai_messages.extend(OllamaProvider._translate_messages(messages))
            oai_tools = OllamaProvider._translate_tools(tools) if tools else None

            kwargs: dict[str, Any] = {
                "model": settings.model,
                "max_tokens": settings.max_tokens,
                "messages": oai_messages,
                "stream": True,
            }
            if oai_tools:
                kwargs["tools"] = oai_tools

            text_accum = ""
            tool_calls_accum: dict[int, dict[str, Any]] = {}  # index -> partial tool call
            usage_info: dict[str, int] = {"input_tokens": 0, "output_tokens": 0}

            stream = await client.chat.completions.create(**kwargs)
            async for chunk in stream:
                if not chunk.choices:
                    # Usage-only chunk at the end
                    if chunk.usage:
                        usage_info["input_tokens"] = chunk.usage.prompt_tokens or 0
                        usage_info["output_tokens"] = chunk.usage.completion_tokens or 0
                    continue

                delta = chunk.choices[0].delta

                # Text content
                if delta.content:
                    text_accum += delta.content
                    await event_queue.put(AgentEvent.text_delta(delta.content))

                # Tool calls (streamed incrementally)
                if delta.tool_calls:
                    for tc_delta in delta.tool_calls:
                        idx = tc_delta.index
                        if idx not in tool_calls_accum:
                            tool_calls_accum[idx] = {
                                "id": tc_delta.id or "",
                                "name": "",
                                "arguments": "",
                            }
                            if tc_delta.function and tc_delta.function.name:
                                tool_calls_accum[idx]["name"] = tc_delta.function.name
                                await event_queue.put(
                                    AgentEvent.tool_use_start(
                                        tc_delta.function.name,
                                        tc_delta.id or "",
                                    )
                                )
                        if tc_delta.function and tc_delta.function.arguments:
                            tool_calls_accum[idx]["arguments"] += tc_delta.function.arguments
                        if tc_delta.id:
                            tool_calls_accum[idx]["id"] = tc_delta.id

                # Check for finish
                if chunk.choices[0].finish_reason:
                    if chunk.usage:
                        usage_info["input_tokens"] = chunk.usage.prompt_tokens or 0
                        usage_info["output_tokens"] = chunk.usage.completion_tokens or 0

            # Build normalized response
            content_blocks: list[dict[str, Any]] = []
            if text_accum:
                content_blocks.append({"type": "text", "text": text_accum})
                await event_queue.put(AgentEvent.text_done(text_accum))

            for idx in sorted(tool_calls_accum.keys()):
                tc = tool_calls_accum[idx]
                try:
                    args = json.loads(tc["arguments"]) if tc["arguments"] else {}
                except json.JSONDecodeError:
                    args = {}
                content_blocks.append({
                    "type": "tool_use",
                    "id": tc["id"] or f"call_{uuid.uuid4().hex[:24]}",
                    "name": tc["name"],
                    "input": args,
                })

            if not content_blocks:
                content_blocks.append({"type": "text", "text": ""})

            return {"content": content_blocks, "usage": usage_info}

        except ImportError:
            error_resp = {
                "content": [
                    {
                        "type": "text",
                        "text": "OpenAI SDK not installed. Install with: pip install 'cadforge[ollama]'",
                    }
                ],
                "usage": {"input_tokens": 0, "output_tokens": 0},
            }
            await event_queue.put(AgentEvent.error(error_resp["content"][0]["text"]))
            return error_resp
        except Exception as e:
            error_resp = {
                "content": [{"type": "text", "text": f"Ollama error: {e}"}],
                "usage": {"input_tokens": 0, "output_tokens": 0},
            }
            await event_queue.put(AgentEvent.error(f"Ollama error: {e}"))
            return error_resp

    def format_tool_results(
        self, tool_results: list[dict[str, Any]]
    ) -> list[dict[str, Any]] | dict[str, Any]:
        oai_messages = []
        for result in tool_results:
            oai_messages.append({
                "role": "tool",
                "tool_call_id": result["tool_use_id"],
                "content": result.get("content", ""),
            })
        return oai_messages


def create_async_provider(
    settings: CadForgeSettings, auth_creds: Any = None
) -> AsyncAnthropicProvider | AsyncOllamaProvider:
    """Factory function to create the appropriate async LLM provider."""
    if settings.provider == "ollama":
        return AsyncOllamaProvider(base_url=settings.base_url)
    return AsyncAnthropicProvider(auth_creds=auth_creds)
