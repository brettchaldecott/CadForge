"""LLM client for Python-side CAD subagent.

Supports Anthropic, OpenAI-compatible (OpenAI / Ollama), and AWS Bedrock.
Auth credentials are forwarded from Node per-request.
"""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any, Protocol

logger = logging.getLogger(__name__)

OAUTH_BETA_HEADER = "oauth-2025-04-20"


class SubagentLLMClient(Protocol):
    """Protocol for subagent LLM clients."""

    model: str
    max_tokens: int

    def call(
        self,
        messages: list[dict[str, Any]],
        system: str,
        tools: list[dict[str, Any]],
    ) -> dict[str, Any]: ...


# ---------------------------------------------------------------------------
# Anthropic
# ---------------------------------------------------------------------------

class AnthropicSubagentClient:
    """Anthropic LLM client for CAD subagent with forwarded auth."""

    def __init__(
        self,
        api_key: str | None = None,
        auth_token: str | None = None,
        model: str = "claude-sonnet-4-5-20250929",
        max_tokens: int = 8192,
    ) -> None:
        self._api_key = api_key
        self._auth_token = auth_token
        self.model = model
        self.max_tokens = max_tokens
        self._client: Any = None

    def _get_client(self) -> Any:
        """Lazy-create the Anthropic client on first use."""
        if self._client is not None:
            return self._client

        import anthropic

        kwargs: dict[str, Any] = {}
        if self._api_key:
            kwargs["api_key"] = self._api_key
        elif self._auth_token:
            kwargs["auth_token"] = self._auth_token
            kwargs["default_headers"] = {"anthropic-beta": OAUTH_BETA_HEADER}
        else:
            raise ValueError("No API key or auth token provided for Anthropic subagent client")

        self._client = anthropic.Anthropic(**kwargs)
        return self._client

    def call(
        self,
        messages: list[dict[str, Any]],
        system: str,
        tools: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Make a synchronous Anthropic API call."""
        client = self._get_client()

        kwargs: dict[str, Any] = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "system": system,
            "messages": messages,
        }
        if tools:
            kwargs["tools"] = tools

        response = client.messages.create(**kwargs)

        content: list[dict[str, Any]] = []
        for block in response.content:
            if block.type == "text":
                content.append({"type": "text", "text": block.text})
            elif block.type == "tool_use":
                content.append({
                    "type": "tool_use",
                    "id": block.id,
                    "name": block.name,
                    "input": block.input,
                })

        return {
            "content": content,
            "stop_reason": response.stop_reason,
            "usage": {
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens,
            },
        }


# ---------------------------------------------------------------------------
# OpenAI-compatible (covers OpenAI and Ollama)
# ---------------------------------------------------------------------------

class OpenAICompatibleSubagentClient:
    """OpenAI-compatible LLM client (works with OpenAI and Ollama)."""

    def __init__(
        self,
        api_key: str = "ollama",
        base_url: str = "http://localhost:11434/v1",
        model: str = "gpt-4o",
        max_tokens: int = 8192,
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url
        self.model = model
        self.max_tokens = max_tokens
        self._client: Any = None

    def _get_client(self) -> Any:
        if self._client is not None:
            return self._client

        from openai import OpenAI

        self._client = OpenAI(
            base_url=self._base_url,
            api_key=self._api_key,
        )
        return self._client

    def call(
        self,
        messages: list[dict[str, Any]],
        system: str,
        tools: list[dict[str, Any]],
    ) -> dict[str, Any]:
        client = self._get_client()

        oai_messages: list[dict[str, Any]] = [{"role": "system", "content": system}]
        oai_messages.extend(_translate_messages(messages))
        oai_tools = _translate_tools(tools) if tools else None

        kwargs: dict[str, Any] = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "messages": oai_messages,
        }
        if oai_tools:
            kwargs["tools"] = oai_tools

        response = client.chat.completions.create(**kwargs)
        return _normalize_openai_response(response)


# ---------------------------------------------------------------------------
# AWS Bedrock
# ---------------------------------------------------------------------------

class BedrockSubagentClient:
    """AWS Bedrock LLM client using the Converse API."""

    def __init__(
        self,
        region: str = "us-east-1",
        profile: str | None = None,
        model: str = "anthropic.claude-sonnet-4-5-20250929-v1:0",
        max_tokens: int = 8192,
    ) -> None:
        self._region = region
        self._profile = profile
        self.model = model
        self.max_tokens = max_tokens
        self._client: Any = None

    def _get_client(self) -> Any:
        if self._client is not None:
            return self._client

        import boto3

        session_kwargs: dict[str, Any] = {"region_name": self._region}
        if self._profile:
            session_kwargs["profile_name"] = self._profile

        session = boto3.Session(**session_kwargs)
        self._client = session.client("bedrock-runtime")
        return self._client

    def call(
        self,
        messages: list[dict[str, Any]],
        system: str,
        tools: list[dict[str, Any]],
    ) -> dict[str, Any]:
        client = self._get_client()

        bedrock_messages = _translate_messages_for_bedrock(messages)
        tool_config = None
        if tools:
            tool_config = {
                "tools": [
                    {
                        "toolSpec": {
                            "name": t["name"],
                            "description": t.get("description", ""),
                            "inputSchema": {"json": t.get("input_schema", {})},
                        }
                    }
                    for t in tools
                ],
            }

        kwargs: dict[str, Any] = {
            "modelId": self.model,
            "system": [{"text": system}],
            "messages": bedrock_messages,
            "inferenceConfig": {"maxTokens": self.max_tokens},
        }
        if tool_config:
            kwargs["toolConfig"] = tool_config

        response = client.converse(**kwargs)

        content: list[dict[str, Any]] = []
        for block in response.get("output", {}).get("message", {}).get("content", []):
            if "text" in block:
                content.append({"type": "text", "text": block["text"]})
            elif "toolUse" in block:
                tu = block["toolUse"]
                content.append({
                    "type": "tool_use",
                    "id": tu.get("toolUseId", ""),
                    "name": tu.get("name", ""),
                    "input": tu.get("input", {}),
                })

        usage = response.get("usage", {})
        return {
            "content": content or [{"type": "text", "text": ""}],
            "stop_reason": response.get("stopReason", "end_turn"),
            "usage": {
                "input_tokens": usage.get("inputTokens", 0),
                "output_tokens": usage.get("outputTokens", 0),
            },
        }


# ---------------------------------------------------------------------------
# LiteLLM (multi-provider via litellm library)
# ---------------------------------------------------------------------------

class LiteLLMSubagentClient:
    """LiteLLM-based client supporting any model via litellm routing.

    LiteLLM returns OpenAI-format responses, so we reuse the existing
    _translate_messages(), _translate_tools(), and _normalize_openai_response()
    helpers to convert to/from our Anthropic-like internal format.
    """

    def __init__(
        self,
        model: str = "minimax/MiniMax-M2.5",
        max_tokens: int = 8192,
        api_key: str | None = None,
    ) -> None:
        self.model = model
        self.max_tokens = max_tokens
        self._api_key = api_key  # optional override; LiteLLM reads env vars by default

    def call(
        self,
        messages: list[dict[str, Any]],
        system: str,
        tools: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Sync call via litellm.completion()."""
        try:
            import litellm
        except ImportError:
            raise RuntimeError(
                "litellm is required for LiteLLMSubagentClient. "
                "Install with: pip install cadforge-engine[agent]"
            )

        oai_messages: list[dict[str, Any]] = [{"role": "system", "content": system}]
        oai_messages.extend(_translate_messages(messages))
        oai_tools = _translate_tools(tools) if tools else None

        kwargs: dict[str, Any] = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "messages": oai_messages,
        }
        if oai_tools:
            kwargs["tools"] = oai_tools
        if self._api_key:
            kwargs["api_key"] = self._api_key

        response = litellm.completion(**kwargs)
        return _normalize_openai_response(response)

    async def acall(
        self,
        messages: list[dict[str, Any]],
        system: str,
        tools: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Async call via litellm.acompletion() — needed for asyncio.gather parallelism."""
        try:
            import litellm
        except ImportError:
            raise RuntimeError(
                "litellm is required for LiteLLMSubagentClient. "
                "Install with: pip install cadforge-engine[agent]"
            )

        oai_messages: list[dict[str, Any]] = [{"role": "system", "content": system}]
        oai_messages.extend(_translate_messages(messages))
        oai_tools = _translate_tools(tools) if tools else None

        kwargs: dict[str, Any] = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "messages": oai_messages,
        }
        if oai_tools:
            kwargs["tools"] = oai_tools
        if self._api_key:
            kwargs["api_key"] = self._api_key

        response = await litellm.acompletion(**kwargs)
        return _normalize_openai_response(response)


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def create_subagent_client(
    provider_config: Any,
    model: str = "claude-sonnet-4-5-20250929",
    max_tokens: int = 8192,
) -> SubagentLLMClient:
    """Create the appropriate subagent LLM client based on provider config.

    Args:
        provider_config: CadSubagentProviderConfig or a legacy auth dict.
        model: Model name to use.
        max_tokens: Max tokens per call.
    """
    # Handle Pydantic model
    if hasattr(provider_config, "provider"):
        provider = provider_config.provider
    elif isinstance(provider_config, dict) and "provider" in provider_config:
        provider = provider_config["provider"]
    else:
        # Legacy: treat as Anthropic auth dict
        api_key = provider_config.get("api_key") if isinstance(provider_config, dict) else None
        auth_token = provider_config.get("auth_token") if isinstance(provider_config, dict) else None
        return AnthropicSubagentClient(  # type: ignore[return-value]
            api_key=api_key,
            auth_token=auth_token,
            model=model,
            max_tokens=max_tokens,
        )

    # Extract fields (works for both Pydantic model and dict)
    def _get(field: str, default: Any = None) -> Any:
        if hasattr(provider_config, field):
            return getattr(provider_config, field) or default
        if isinstance(provider_config, dict):
            return provider_config.get(field) or default
        return default

    if provider == "anthropic":
        return AnthropicSubagentClient(  # type: ignore[return-value]
            api_key=_get("api_key"),
            auth_token=_get("auth_token"),
            model=model,
            max_tokens=max_tokens,
        )
    elif provider in ("openai", "ollama"):
        base_url = _get("base_url")
        if provider == "ollama" and not base_url:
            base_url = "http://localhost:11434/v1"
        elif provider == "openai" and not base_url:
            base_url = "https://api.openai.com/v1"
        return OpenAICompatibleSubagentClient(  # type: ignore[return-value]
            api_key=_get("api_key", "ollama" if provider == "ollama" else ""),
            base_url=base_url,
            model=model,
            max_tokens=max_tokens,
        )
    elif provider == "bedrock":
        return BedrockSubagentClient(  # type: ignore[return-value]
            region=_get("aws_region", "us-east-1"),
            profile=_get("aws_profile"),
            model=model,
            max_tokens=max_tokens,
        )
    elif provider == "litellm":
        return LiteLLMSubagentClient(  # type: ignore[return-value]
            model=model,
            max_tokens=max_tokens,
            api_key=_get("api_key"),
        )
    else:
        raise ValueError(f"Unknown provider: {provider}")


# ---------------------------------------------------------------------------
# OpenAI format translation helpers
# ---------------------------------------------------------------------------

def _translate_tools(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Anthropic tool defs -> OpenAI function format."""
    return [
        {
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t.get("description", ""),
                "parameters": t.get("input_schema", {}),
            },
        }
        for t in tools
    ]


def _translate_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Anthropic-style messages -> OpenAI format."""
    result: list[dict[str, Any]] = []
    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content")

        if isinstance(content, str):
            result.append({"role": role, "content": content})
            continue

        if not isinstance(content, list):
            result.append({"role": role, "content": str(content)})
            continue

        if role == "assistant":
            text_parts: list[str] = []
            tool_calls: list[dict[str, Any]] = []
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
            result.append(assistant_msg)

        elif role == "user":
            tool_results = [b for b in content if b.get("type") == "tool_result"]
            if tool_results:
                for r in tool_results:
                    result.append({
                        "role": "tool",
                        "tool_call_id": r["tool_use_id"],
                        "content": r.get("content", ""),
                    })
            else:
                # Handle mixed text + image content for OpenAI
                oai_parts: list[dict[str, Any]] = []
                for b in content:
                    if b.get("type") == "text":
                        oai_parts.append({"type": "text", "text": b["text"]})
                    elif b.get("type") == "image":
                        src = b.get("source", {})
                        media = src.get("media_type", "image/png")
                        data = src.get("data", "")
                        oai_parts.append({
                            "type": "image_url",
                            "image_url": {"url": f"data:{media};base64,{data}"},
                        })
                if oai_parts:
                    result.append({"role": "user", "content": oai_parts})
                else:
                    result.append({"role": "user", "content": ""})
        else:
            result.append({"role": role, "content": str(content)})

    return result


def _normalize_openai_response(response: Any) -> dict[str, Any]:
    """OpenAI ChatCompletion -> Anthropic-style response."""
    choice = response.choices[0] if response.choices else None
    if choice is None:
        return {
            "content": [{"type": "text", "text": "No response from model"}],
            "stop_reason": "end_turn",
            "usage": {"input_tokens": 0, "output_tokens": 0},
        }

    message = choice.message
    content_blocks: list[dict[str, Any]] = []

    if message.content:
        content_blocks.append({"type": "text", "text": message.content})

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
        "stop_reason": choice.finish_reason or "end_turn",
        "usage": {
            "input_tokens": usage.prompt_tokens if usage else 0,
            "output_tokens": usage.completion_tokens if usage else 0,
        },
    }


def _translate_messages_for_bedrock(
    messages: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Anthropic-style messages -> Bedrock Converse format."""
    result: list[dict[str, Any]] = []
    for msg in messages:
        content = msg.get("content")
        role = msg.get("role", "user")

        if isinstance(content, str):
            result.append({"role": role, "content": [{"text": content}]})
            continue

        if not isinstance(content, list):
            result.append({"role": role, "content": [{"text": str(content)}]})
            continue

        bedrock_content: list[dict[str, Any]] = []
        for block in content:
            if block.get("type") == "text":
                bedrock_content.append({"text": block["text"]})
            elif block.get("type") == "image":
                import base64
                src = block.get("source", {})
                data = src.get("data", "")
                fmt = src.get("media_type", "image/png").split("/")[-1]
                bedrock_content.append({
                    "image": {
                        "format": fmt,
                        "source": {"bytes": base64.b64decode(data)},
                    }
                })
            elif block.get("type") == "tool_use":
                bedrock_content.append({
                    "toolUse": {
                        "toolUseId": block["id"],
                        "name": block["name"],
                        "input": block.get("input", {}),
                    }
                })
            elif block.get("type") == "tool_result":
                bedrock_content.append({
                    "toolResult": {
                        "toolUseId": block["tool_use_id"],
                        "content": [{"text": block.get("content", "")}],
                    }
                })

        if bedrock_content:
            result.append({"role": role, "content": bedrock_content})

    return result
