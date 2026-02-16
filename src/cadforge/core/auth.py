"""Authentication for CadForge.

Supports three auth methods in priority order:
1. ANTHROPIC_API_KEY environment variable (standard API key)
2. ANTHROPIC_AUTH_TOKEN environment variable (OAuth token)
3. Claude Code OAuth credentials from macOS Keychain (automatic)

When using Claude Code OAuth, tokens are refreshed automatically
before expiry.
"""

from __future__ import annotations

import json
import os
import subprocess
import time
from dataclasses import dataclass
from typing import Any


OAUTH_CLIENT_ID = "9d1c250a-e61b-44d9-88ed-5944d1962f5e"
OAUTH_TOKEN_URL = "https://console.anthropic.com/v1/oauth/token"
OAUTH_BETA_HEADER = "oauth-2025-04-20"

# Refresh when less than 10 minutes remain
TOKEN_REFRESH_BUFFER_SECS = 600


@dataclass
class AuthCredentials:
    """Resolved authentication credentials."""
    api_key: str | None = None
    auth_token: str | None = None
    refresh_token: str | None = None
    expires_at: float | None = None
    source: str = "none"  # "api_key", "env_token", "claude_code"

    @property
    def is_valid(self) -> bool:
        return self.api_key is not None or self.auth_token is not None

    @property
    def needs_refresh(self) -> bool:
        if self.expires_at is None or self.refresh_token is None:
            return False
        return time.time() * 1000 >= self.expires_at - (TOKEN_REFRESH_BUFFER_SECS * 1000)

    @property
    def uses_oauth(self) -> bool:
        return self.source in ("env_token", "claude_code")


def resolve_auth() -> AuthCredentials:
    """Resolve authentication credentials.

    Priority:
    1. ANTHROPIC_API_KEY env var
    2. ANTHROPIC_AUTH_TOKEN env var
    3. Claude Code OAuth from macOS Keychain
    """
    # 1. API key
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if api_key:
        return AuthCredentials(api_key=api_key, source="api_key")

    # 2. Explicit auth token
    auth_token = os.environ.get("ANTHROPIC_AUTH_TOKEN")
    if auth_token:
        return AuthCredentials(auth_token=auth_token, source="env_token")

    # 3. Claude Code OAuth from keychain
    creds = _read_claude_code_keychain()
    if creds:
        return creds

    return AuthCredentials(source="none")


def _read_claude_code_keychain() -> AuthCredentials | None:
    """Read Claude Code OAuth credentials from macOS Keychain."""
    try:
        username = os.environ.get("USER", "")
        result = subprocess.run(
            [
                "security", "find-generic-password",
                "-s", "Claude Code-credentials",
                "-a", username,
                "-w",
            ],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode != 0:
            return None

        data = json.loads(result.stdout.strip())
        oauth = data.get("claudeAiOauth")
        if not oauth:
            return None

        return AuthCredentials(
            auth_token=oauth.get("accessToken"),
            refresh_token=oauth.get("refreshToken"),
            expires_at=oauth.get("expiresAt"),
            source="claude_code",
        )
    except (subprocess.TimeoutExpired, json.JSONDecodeError, OSError, KeyError):
        return None


def refresh_oauth_token(creds: AuthCredentials) -> AuthCredentials:
    """Refresh an expired OAuth access token.

    Returns updated credentials with new access token.
    """
    if not creds.refresh_token:
        return creds

    try:
        import httpx
        response = httpx.post(
            OAUTH_TOKEN_URL,
            data={
                "grant_type": "refresh_token",
                "client_id": OAUTH_CLIENT_ID,
                "refresh_token": creds.refresh_token,
            },
            timeout=15,
        )
        response.raise_for_status()
        data = response.json()

        new_creds = AuthCredentials(
            auth_token=data.get("access_token", creds.auth_token),
            refresh_token=data.get("refresh_token", creds.refresh_token),
            expires_at=time.time() * 1000 + data.get("expires_in", 28800) * 1000,
            source=creds.source,
        )

        # Update keychain if this came from Claude Code
        if creds.source == "claude_code":
            _update_claude_code_keychain(new_creds)

        return new_creds
    except Exception:
        return creds


def _update_claude_code_keychain(creds: AuthCredentials) -> None:
    """Write updated OAuth tokens back to macOS Keychain."""
    try:
        username = os.environ.get("USER", "")

        # Read existing data
        result = subprocess.run(
            [
                "security", "find-generic-password",
                "-s", "Claude Code-credentials",
                "-a", username,
                "-w",
            ],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode != 0:
            return

        data = json.loads(result.stdout.strip())
        oauth = data.get("claudeAiOauth", {})
        oauth["accessToken"] = creds.auth_token
        if creds.refresh_token:
            oauth["refreshToken"] = creds.refresh_token
        if creds.expires_at:
            oauth["expiresAt"] = creds.expires_at
        data["claudeAiOauth"] = oauth

        new_value = json.dumps(data)

        # Delete and re-add (keychain doesn't support in-place update)
        subprocess.run(
            [
                "security", "delete-generic-password",
                "-s", "Claude Code-credentials",
                "-a", username,
            ],
            capture_output=True,
            timeout=5,
        )
        subprocess.run(
            [
                "security", "add-generic-password",
                "-s", "Claude Code-credentials",
                "-a", username,
                "-w", new_value,
            ],
            capture_output=True,
            timeout=5,
        )
    except Exception:
        pass  # Non-critical — token still works in memory


def _build_client_kwargs(creds: AuthCredentials) -> dict[str, Any]:
    """Build keyword arguments for Anthropic client constructors."""
    kwargs: dict[str, Any] = {}
    if creds.api_key:
        kwargs["api_key"] = creds.api_key
    elif creds.auth_token:
        kwargs["auth_token"] = creds.auth_token
        kwargs["default_headers"] = {"anthropic-beta": OAUTH_BETA_HEADER}
    return kwargs


def create_anthropic_client(creds: AuthCredentials) -> Any:
    """Create an Anthropic client with the resolved credentials.

    Handles OAuth token refresh if needed.
    """
    import anthropic

    # Refresh if needed
    if creds.needs_refresh:
        creds = refresh_oauth_token(creds)

    kwargs = _build_client_kwargs(creds)
    return anthropic.Anthropic(**kwargs), creds


def create_async_anthropic_client(creds: AuthCredentials) -> Any:
    """Create an async Anthropic client with the resolved credentials.

    Identical to create_anthropic_client() but returns AsyncAnthropic.
    """
    import anthropic

    if creds.needs_refresh:
        creds = refresh_oauth_token(creds)

    kwargs = _build_client_kwargs(creds)
    return anthropic.AsyncAnthropic(**kwargs), creds
