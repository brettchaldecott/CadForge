"""LLM client for Python-side CAD subagent.

Auth credentials are forwarded from Node per-request.
Uses the Anthropic SDK to make synchronous API calls.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

OAUTH_BETA_HEADER = "oauth-2025-04-20"


class SubagentLLMClient:
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
            raise ValueError("No API key or auth token provided for subagent LLM client")

        self._client = anthropic.Anthropic(**kwargs)
        return self._client

    def call(
        self,
        messages: list[dict[str, Any]],
        system: str,
        tools: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Make a synchronous Anthropic API call.

        Returns a normalized response dict with 'content' and 'stop_reason'.
        """
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

        # Normalize content blocks
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
