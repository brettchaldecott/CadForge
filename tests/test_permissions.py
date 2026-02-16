"""Tests for CadForge permission system."""

from __future__ import annotations

import pytest

from cadforge.core.permissions import (
    PermissionResult,
    ToolCall,
    evaluate_permission,
    format_permission_prompt,
    matches_rule,
    merge_permissions,
    parse_rule,
)


class TestParseRule:
    def test_simple_rule(self):
        assert parse_rule("ReadFile(*)") == ("ReadFile", "*")

    def test_rule_with_path(self):
        assert parse_rule("WriteFile(**/.env)") == ("WriteFile", "**/.env")

    def test_rule_with_colon(self):
        assert parse_rule("Bash(rm:*)") == ("Bash", "rm:*")

    def test_invalid_rule_no_parens(self):
        with pytest.raises(ValueError, match="Invalid permission rule"):
            parse_rule("ReadFile")

    def test_invalid_rule_empty(self):
        with pytest.raises(ValueError, match="Invalid permission rule"):
            parse_rule("")

    def test_rule_with_whitespace(self):
        assert parse_rule("  ReadFile(*)  ") == ("ReadFile", "*")


class TestMatchesRule:
    def test_wildcard_matches_all(self):
        tc = ToolCall("ReadFile", "src/main.py")
        assert matches_rule(tc, "ReadFile(*)") is True

    def test_exact_match(self):
        tc = ToolCall("WriteFile", ".env")
        assert matches_rule(tc, "WriteFile(.env)") is True

    def test_glob_match(self):
        tc = ToolCall("WriteFile", "secrets/.env")
        assert matches_rule(tc, "WriteFile(**/.env)") is True

    def test_no_match_wrong_tool(self):
        tc = ToolCall("WriteFile", "test.py")
        assert matches_rule(tc, "ReadFile(*)") is False

    def test_no_match_wrong_pattern(self):
        tc = ToolCall("Bash", "ls -la")
        assert matches_rule(tc, "Bash(rm:*)") is False

    def test_colon_pattern_match(self):
        tc = ToolCall("Bash", "rm:*.py")
        assert matches_rule(tc, "Bash(rm:*)") is True

    def test_invalid_rule_returns_false(self):
        tc = ToolCall("ReadFile", "test.py")
        assert matches_rule(tc, "invalid") is False


class TestEvaluatePermission:
    @pytest.fixture
    def permissions(self):
        return {
            "deny": ["Bash(rm:*)", "Bash(sudo:*)", "WriteFile(**/.env)"],
            "allow": ["ReadFile(*)", "SearchVault(*)", "AnalyzeMesh(*)"],
            "ask": ["ExecuteCadQuery(*)", "WriteFile(*)", "Bash(*)"],
        }

    def test_deny_blocks(self, permissions):
        tc = ToolCall("Bash", "rm:*.py")
        assert evaluate_permission(tc, permissions) == PermissionResult.DENY

    def test_deny_sudo(self, permissions):
        tc = ToolCall("Bash", "sudo:apt-get")
        assert evaluate_permission(tc, permissions) == PermissionResult.DENY

    def test_deny_env_file(self, permissions):
        tc = ToolCall("WriteFile", "config/.env")
        assert evaluate_permission(tc, permissions) == PermissionResult.DENY

    def test_allow_read(self, permissions):
        tc = ToolCall("ReadFile", "any/path.py")
        assert evaluate_permission(tc, permissions) == PermissionResult.ALLOW

    def test_allow_search(self, permissions):
        tc = ToolCall("SearchVault", "wall thickness PLA")
        assert evaluate_permission(tc, permissions) == PermissionResult.ALLOW

    def test_ask_cadquery(self, permissions):
        tc = ToolCall("ExecuteCadQuery", "cube.py")
        assert evaluate_permission(tc, permissions) == PermissionResult.ASK

    def test_ask_write(self, permissions):
        tc = ToolCall("WriteFile", "output/test.stl")
        assert evaluate_permission(tc, permissions) == PermissionResult.ASK

    def test_ask_bash_general(self, permissions):
        tc = ToolCall("Bash", "ls -la")
        assert evaluate_permission(tc, permissions) == PermissionResult.ASK

    def test_unknown_tool_defaults_to_ask(self, permissions):
        tc = ToolCall("UnknownTool", "arg")
        assert evaluate_permission(tc, permissions) == PermissionResult.ASK

    def test_deny_takes_precedence_over_allow(self):
        perms = {
            "deny": ["ReadFile(secret/*)"],
            "allow": ["ReadFile(*)"],
            "ask": [],
        }
        tc = ToolCall("ReadFile", "secret/key.pem")
        assert evaluate_permission(tc, perms) == PermissionResult.DENY

    def test_allow_takes_precedence_over_ask(self):
        perms = {
            "deny": [],
            "allow": ["Bash(ls:*)"],
            "ask": ["Bash(*)"],
        }
        tc = ToolCall("Bash", "ls:dir")
        assert evaluate_permission(tc, perms) == PermissionResult.ALLOW

    def test_empty_permissions_defaults_to_ask(self):
        tc = ToolCall("Anything", "arg")
        assert evaluate_permission(tc, {}) == PermissionResult.ASK


class TestMergePermissions:
    def test_later_overrides_earlier(self):
        p1 = {"deny": ["Bash(rm:*)"], "allow": ["ReadFile(*)"], "ask": []}
        p2 = {"deny": ["Bash(rm:*)", "Bash(sudo:*)"], "allow": [], "ask": ["ReadFile(*)"]}
        result = merge_permissions(p1, p2)
        assert result["deny"] == ["Bash(rm:*)", "Bash(sudo:*)"]
        assert result["allow"] == []
        assert result["ask"] == ["ReadFile(*)"]

    def test_partial_override(self):
        p1 = {"deny": ["Bash(rm:*)"], "allow": ["ReadFile(*)"], "ask": []}
        p2 = {"deny": ["Bash(sudo:*)"]}
        result = merge_permissions(p1, p2)
        assert result["deny"] == ["Bash(sudo:*)"]
        assert result["allow"] == ["ReadFile(*)"]  # unchanged

    def test_empty_merge(self):
        result = merge_permissions()
        assert result == {"deny": [], "allow": [], "ask": []}


class TestToolCall:
    def test_str(self):
        tc = ToolCall("ReadFile", "test.py")
        assert str(tc) == "ReadFile(test.py)"

    def test_default_argument(self):
        tc = ToolCall("ReadFile")
        assert tc.argument == "*"


class TestFormatPermissionPrompt:
    def test_format(self):
        tc = ToolCall("ExecuteCadQuery", "cube.py")
        prompt = format_permission_prompt(tc)
        assert "ExecuteCadQuery" in prompt
        assert "cube.py" in prompt
        assert "Y/n" in prompt
