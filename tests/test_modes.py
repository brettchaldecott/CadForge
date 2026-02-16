"""Tests for CadForge interaction modes."""

from __future__ import annotations

import pytest

from cadforge.chat.modes import (
    PLAN_MODE_TOOLS,
    PROCEED_PHRASES,
    InteractionMode,
    get_mode_tools,
    get_plan_mode_permissions,
    has_proceed_intent,
)


class TestInteractionMode:
    def test_values(self):
        assert InteractionMode.AGENT.value == "agent"
        assert InteractionMode.PLAN.value == "plan"
        assert InteractionMode.ASK.value == "ask"

    def test_prompt_prefix(self):
        assert InteractionMode.AGENT.prompt_prefix == "cadforge:agent> "
        assert InteractionMode.PLAN.prompt_prefix == "cadforge:plan> "
        assert InteractionMode.ASK.prompt_prefix == "cadforge:ask> "

    def test_display_name(self):
        assert InteractionMode.AGENT.display_name == "AGENT"
        assert InteractionMode.PLAN.display_name == "PLAN"
        assert InteractionMode.ASK.display_name == "ASK"

    def test_colors(self):
        assert InteractionMode.AGENT.color == "green"
        assert InteractionMode.PLAN.color == "yellow"
        assert InteractionMode.ASK.color == "cyan"

    def test_cycle_agent_to_plan(self):
        assert InteractionMode.AGENT.next() == InteractionMode.PLAN

    def test_cycle_plan_to_ask(self):
        assert InteractionMode.PLAN.next() == InteractionMode.ASK

    def test_cycle_ask_to_agent(self):
        assert InteractionMode.ASK.next() == InteractionMode.AGENT

    def test_full_cycle(self):
        mode = InteractionMode.AGENT
        mode = mode.next()
        assert mode == InteractionMode.PLAN
        mode = mode.next()
        assert mode == InteractionMode.ASK
        mode = mode.next()
        assert mode == InteractionMode.AGENT


class TestGetModeTools:
    def test_agent_returns_none(self):
        result = get_mode_tools(InteractionMode.AGENT)
        assert result is None

    def test_plan_returns_read_only_set(self):
        result = get_mode_tools(InteractionMode.PLAN)
        assert result is not None
        assert isinstance(result, frozenset)
        assert result == PLAN_MODE_TOOLS

    def test_plan_includes_expected_tools(self):
        result = get_mode_tools(InteractionMode.PLAN)
        assert "ReadFile" in result
        assert "ListFiles" in result
        assert "SearchVault" in result
        assert "Bash" in result
        assert "GetPrinter" in result
        assert "Task" in result

    def test_plan_excludes_write_tools(self):
        result = get_mode_tools(InteractionMode.PLAN)
        assert "WriteFile" not in result
        assert "ExecuteCadQuery" not in result
        assert "ExportModel" not in result
        assert "ShowPreview" not in result

    def test_ask_returns_empty_set(self):
        result = get_mode_tools(InteractionMode.ASK)
        assert result is not None
        assert isinstance(result, frozenset)
        assert len(result) == 0


class TestPlanModePermissions:
    def test_returns_dict_with_deny_allow_ask(self):
        perms = get_plan_mode_permissions()
        assert "deny" in perms
        assert "allow" in perms
        assert "ask" in perms

    def test_denies_write_tools(self):
        perms = get_plan_mode_permissions()
        deny_strs = " ".join(perms["deny"])
        assert "WriteFile" in deny_strs
        assert "ExecuteCadQuery" in deny_strs
        assert "ExportModel" in deny_strs

    def test_allows_read_tools(self):
        perms = get_plan_mode_permissions()
        allow_strs = " ".join(perms["allow"])
        assert "ReadFile" in allow_strs
        assert "ListFiles" in allow_strs
        assert "SearchVault" in allow_strs

    def test_ask_is_empty(self):
        perms = get_plan_mode_permissions()
        assert perms["ask"] == []


class TestHasProceedIntent:
    """Tests for proceed intent detection in plan mode."""

    def test_exact_proceed(self):
        assert has_proceed_intent("proceed") is True

    def test_please_proceed(self):
        assert has_proceed_intent("please proceed") is True

    def test_go_ahead(self):
        assert has_proceed_intent("go ahead") is True

    def test_yes_go_ahead(self):
        assert has_proceed_intent("yes, go ahead") is True

    def test_do_it(self):
        assert has_proceed_intent("do it") is True

    def test_execute(self):
        assert has_proceed_intent("execute") is True

    def test_implement(self):
        assert has_proceed_intent("implement") is True

    def test_build_it(self):
        assert has_proceed_intent("build it") is True

    def test_lets_go(self):
        assert has_proceed_intent("let's go") is True

    def test_case_insensitive(self):
        assert has_proceed_intent("PROCEED") is True
        assert has_proceed_intent("Go Ahead") is True
        assert has_proceed_intent("Please EXECUTE the plan") is True

    def test_with_whitespace(self):
        assert has_proceed_intent("  proceed  ") is True

    def test_normal_plan_question_no_match(self):
        assert has_proceed_intent("how should I design this?") is False

    def test_empty_string(self):
        assert has_proceed_intent("") is False

    def test_unrelated_input(self):
        assert has_proceed_intent("what files are in this project?") is False

    def test_plan_request(self):
        assert has_proceed_intent("plan the architecture for a REST API") is False

    def test_all_phrases_detected(self):
        for phrase in PROCEED_PHRASES:
            assert has_proceed_intent(phrase) is True, f"Failed for: {phrase}"
