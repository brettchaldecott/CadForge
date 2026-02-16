"""Tests for CadForge hooks system."""

from __future__ import annotations

import pytest

from cadforge.core.hooks import (
    HookConfig,
    HookDefinition,
    HookEvent,
    HookResult,
    execute_hook,
    get_matching_hooks,
    load_hook_configs,
    matches_hook,
    run_hooks,
)


class TestMatchesHook:
    def test_wildcard_matches_all(self):
        assert matches_hook("*", "ExecuteCadQuery", "code") is True

    def test_tool_name_match(self):
        assert matches_hook("ExecuteCadQuery(*)", "ExecuteCadQuery", "code") is True

    def test_tool_name_mismatch(self):
        assert matches_hook("Bash(*)", "ExecuteCadQuery", "code") is False

    def test_pattern_match(self):
        assert matches_hook("Bash(ls:*)", "Bash", "ls:dir") is True

    def test_pattern_mismatch(self):
        assert matches_hook("Bash(rm:*)", "Bash", "ls:dir") is False

    def test_bare_tool_name(self):
        assert matches_hook("Bash", "Bash") is True

    def test_bare_tool_name_mismatch(self):
        assert matches_hook("Bash", "ReadFile") is False


class TestHookDefinition:
    def test_from_dict(self):
        d = {"type": "command", "command": "echo hello", "timeout": 10}
        h = HookDefinition.from_dict(d)
        assert h.command == "echo hello"
        assert h.timeout == 10

    def test_defaults(self):
        d = {"command": "echo test"}
        h = HookDefinition.from_dict(d)
        assert h.type == "command"
        assert h.timeout == 30


class TestHookConfig:
    def test_from_dict(self):
        d = {
            "event": "PreToolUse",
            "matcher": "ExecuteCadQuery(*)",
            "hooks": [{"type": "command", "command": "echo pre"}],
        }
        c = HookConfig.from_dict(d)
        assert c.event == HookEvent.PRE_TOOL_USE
        assert c.matcher == "ExecuteCadQuery(*)"
        assert len(c.hooks) == 1


class TestHookResult:
    def test_success(self):
        r = HookResult(exit_code=0, stdout="ok", stderr="")
        assert r.success is True
        assert r.blocked is False
        assert r.error is False

    def test_blocked(self):
        r = HookResult(exit_code=2, stdout="", stderr="blocked")
        assert r.success is False
        assert r.blocked is True
        assert r.error is False

    def test_error(self):
        r = HookResult(exit_code=1, stdout="", stderr="fail")
        assert r.success is False
        assert r.blocked is False
        assert r.error is True


class TestExecuteHook:
    def test_echo_command(self):
        hook = HookDefinition(type="command", command="echo hello")
        result = execute_hook(hook)
        assert result.success is True
        assert "hello" in result.stdout

    def test_failing_command(self):
        hook = HookDefinition(type="command", command="exit 1")
        result = execute_hook(hook)
        assert result.success is False
        assert result.exit_code == 1

    def test_blocking_command(self):
        hook = HookDefinition(type="command", command="exit 2")
        result = execute_hook(hook)
        assert result.blocked is True

    def test_timeout(self):
        hook = HookDefinition(type="command", command="sleep 10", timeout=1)
        result = execute_hook(hook)
        assert result.success is False
        assert "timed out" in result.stderr.lower()

    def test_env_vars(self):
        hook = HookDefinition(type="command", command="echo $MY_VAR")
        result = execute_hook(hook, env={"MY_VAR": "test_value"})
        assert "test_value" in result.stdout

    def test_stderr_capture(self):
        hook = HookDefinition(type="command", command="echo error >&2")
        result = execute_hook(hook)
        assert "error" in result.stderr


class TestGetMatchingHooks:
    @pytest.fixture
    def configs(self):
        return [
            HookConfig(
                event=HookEvent.PRE_TOOL_USE,
                matcher="ExecuteCadQuery(*)",
                hooks=[HookDefinition(type="command", command="echo pre-cad")],
            ),
            HookConfig(
                event=HookEvent.POST_TOOL_USE,
                matcher="ExecuteCadQuery(*)",
                hooks=[HookDefinition(type="command", command="echo post-cad")],
            ),
            HookConfig(
                event=HookEvent.PRE_TOOL_USE,
                matcher="Bash(*)",
                hooks=[HookDefinition(type="command", command="echo pre-bash")],
            ),
            HookConfig(
                event=HookEvent.SESSION_START,
                matcher="*",
                hooks=[HookDefinition(type="command", command="echo start")],
            ),
        ]

    def test_pre_tool_match(self, configs):
        hooks = get_matching_hooks(configs, HookEvent.PRE_TOOL_USE, "ExecuteCadQuery")
        assert len(hooks) == 1
        assert "pre-cad" in hooks[0].command

    def test_post_tool_match(self, configs):
        hooks = get_matching_hooks(configs, HookEvent.POST_TOOL_USE, "ExecuteCadQuery")
        assert len(hooks) == 1
        assert "post-cad" in hooks[0].command

    def test_no_match(self, configs):
        hooks = get_matching_hooks(configs, HookEvent.PRE_TOOL_USE, "ReadFile")
        assert len(hooks) == 0

    def test_session_start(self, configs):
        hooks = get_matching_hooks(configs, HookEvent.SESSION_START)
        assert len(hooks) == 1


class TestRunHooks:
    def test_run_matching_hooks(self):
        configs = [
            HookConfig(
                event=HookEvent.PRE_TOOL_USE,
                matcher="*",
                hooks=[HookDefinition(type="command", command="echo ok")],
            ),
        ]
        results = run_hooks(configs, HookEvent.PRE_TOOL_USE, "Bash", "ls")
        assert len(results) == 1
        assert results[0].success

    def test_stops_on_block(self):
        configs = [
            HookConfig(
                event=HookEvent.PRE_TOOL_USE,
                matcher="*",
                hooks=[
                    HookDefinition(type="command", command="exit 2"),
                    HookDefinition(type="command", command="echo should-not-run"),
                ],
            ),
        ]
        results = run_hooks(configs, HookEvent.PRE_TOOL_USE, "Bash")
        assert len(results) == 1
        assert results[0].blocked


class TestLoadHookConfigs:
    def test_valid_configs(self):
        data = [
            {
                "event": "PreToolUse",
                "matcher": "ExecuteCadQuery(*)",
                "hooks": [{"type": "command", "command": "echo test"}],
            },
        ]
        configs = load_hook_configs(data)
        assert len(configs) == 1
        assert configs[0].event == HookEvent.PRE_TOOL_USE

    def test_skips_invalid(self):
        data = [
            {"invalid": "data"},
            {
                "event": "PostToolUse",
                "matcher": "*",
                "hooks": [{"command": "echo ok"}],
            },
        ]
        configs = load_hook_configs(data)
        assert len(configs) == 1

    def test_empty_list(self):
        assert load_hook_configs([]) == []
