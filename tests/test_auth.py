"""Tests for CadForge authentication."""

from __future__ import annotations

import json
import os
import time
from unittest.mock import MagicMock, patch

import pytest

from cadforge.core.auth import (
    AuthCredentials,
    resolve_auth,
    _read_claude_code_keychain,
)


class TestAuthCredentials:
    def test_api_key_valid(self):
        c = AuthCredentials(api_key="sk-ant-api03-test")
        assert c.is_valid is True
        assert c.uses_oauth is False

    def test_auth_token_valid(self):
        c = AuthCredentials(auth_token="sk-ant-oat01-test", source="claude_code")
        assert c.is_valid is True
        assert c.uses_oauth is True

    def test_none_invalid(self):
        c = AuthCredentials()
        assert c.is_valid is False

    def test_needs_refresh_when_expired(self):
        c = AuthCredentials(
            auth_token="tok",
            refresh_token="ref",
            expires_at=time.time() * 1000 - 1000,  # Already expired
        )
        assert c.needs_refresh is True

    def test_no_refresh_when_fresh(self):
        c = AuthCredentials(
            auth_token="tok",
            refresh_token="ref",
            expires_at=time.time() * 1000 + 3600_000,  # 1 hour from now
        )
        assert c.needs_refresh is False

    def test_no_refresh_without_refresh_token(self):
        c = AuthCredentials(
            auth_token="tok",
            expires_at=time.time() * 1000 - 1000,
        )
        assert c.needs_refresh is False


class TestResolveAuth:
    def test_api_key_from_env(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-api03-test")
        monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
        creds = resolve_auth()
        assert creds.source == "api_key"
        assert creds.api_key == "sk-ant-api03-test"

    def test_auth_token_from_env(self, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "sk-ant-oat01-test")
        creds = resolve_auth()
        assert creds.source == "env_token"
        assert creds.auth_token == "sk-ant-oat01-test"

    def test_api_key_takes_precedence(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-api03-key")
        monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "sk-ant-oat01-token")
        creds = resolve_auth()
        assert creds.source == "api_key"

    @patch("cadforge.core.auth._read_claude_code_keychain")
    def test_falls_back_to_keychain(self, mock_keychain, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
        mock_keychain.return_value = AuthCredentials(
            auth_token="sk-ant-oat01-from-keychain",
            source="claude_code",
        )
        creds = resolve_auth()
        assert creds.source == "claude_code"
        assert creds.auth_token == "sk-ant-oat01-from-keychain"

    @patch("cadforge.core.auth._read_claude_code_keychain")
    def test_no_auth_available(self, mock_keychain, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
        mock_keychain.return_value = None
        creds = resolve_auth()
        assert creds.source == "none"
        assert creds.is_valid is False


class TestReadKeychainParsing:
    @patch("subprocess.run")
    def test_parses_keychain_json(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps({
                "claudeAiOauth": {
                    "accessToken": "sk-ant-oat01-abc",
                    "refreshToken": "sk-ant-ort01-xyz",
                    "expiresAt": 9999999999999,
                }
            }),
        )
        creds = _read_claude_code_keychain()
        assert creds is not None
        assert creds.auth_token == "sk-ant-oat01-abc"
        assert creds.refresh_token == "sk-ant-ort01-xyz"
        assert creds.source == "claude_code"

    @patch("subprocess.run")
    def test_returns_none_on_failure(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1, stdout="")
        assert _read_claude_code_keychain() is None

    @patch("subprocess.run")
    def test_returns_none_on_bad_json(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="not json")
        assert _read_claude_code_keychain() is None

    @patch("subprocess.run")
    def test_returns_none_on_missing_oauth(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps({"someOtherKey": {}}),
        )
        assert _read_claude_code_keychain() is None
