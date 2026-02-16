"""Tests for the persistent prompt bar."""

from __future__ import annotations

import io
import os
import sys
from unittest.mock import patch

import pytest

from cadforge.chat.prompt_bar import BAR_HEIGHT, PromptBar


@pytest.fixture
def bar():
    """Create a PromptBar with TTY flag forced on."""
    pb = PromptBar()
    pb._is_tty = True
    return pb


@pytest.fixture
def non_tty_bar():
    """Create a PromptBar in non-TTY mode."""
    pb = PromptBar()
    pb._is_tty = False
    return pb


class TestInitialState:
    def test_default_mode(self, bar):
        assert bar._mode_label == "AGENT"
        assert bar._mode_color_code == "32"  # green

    def test_not_busy_by_default(self, bar):
        assert not bar._busy
        assert bar._status_text == ""

    def test_not_active_by_default(self, bar):
        assert not bar._active


class TestModeChanges:
    def test_set_mode_updates_label(self, bar):
        bar.set_mode("PLAN", "yellow")
        assert bar._mode_label == "PLAN"
        assert bar._mode_color_code == "33"

    def test_set_mode_cyan(self, bar):
        bar.set_mode("ASK", "cyan")
        assert bar._mode_label == "ASK"
        assert bar._mode_color_code == "36"

    def test_set_mode_unknown_color_defaults_green(self, bar):
        bar.set_mode("CUSTOM", "magenta")
        assert bar._mode_color_code == "32"  # falls back to green


class TestBusyIdle:
    def test_set_busy(self, bar):
        bar.set_busy("Thinking...")
        assert bar._busy is True
        assert bar._status_text == "Thinking..."

    def test_set_idle(self, bar):
        bar.set_busy("Working...")
        bar.set_idle()
        assert bar._busy is False
        assert bar._status_text == ""

    def test_update_status(self, bar):
        bar.set_busy("Thinking...")
        bar.update_status("Executing Bash...")
        assert bar._status_text == "Executing Bash..."


class TestActivateDeactivate:
    @patch("os.get_terminal_size")
    @patch("signal.getsignal")
    @patch("signal.signal")
    def test_activate_sets_scroll_region(
        self, mock_signal, mock_getsignal, mock_termsize, bar
    ):
        mock_termsize.return_value = os.terminal_size((80, 24))
        mock_getsignal.return_value = None

        bar.activate()
        assert bar._active is True

    @patch("os.get_terminal_size")
    @patch("signal.getsignal")
    @patch("signal.signal")
    def test_deactivate_resets_state(
        self, mock_signal, mock_getsignal, mock_termsize, bar
    ):
        mock_termsize.return_value = os.terminal_size((80, 24))
        mock_getsignal.return_value = None

        bar.activate()
        bar.deactivate()
        assert bar._active is False

    def test_activate_noop_when_not_tty(self, non_tty_bar):
        non_tty_bar.activate()
        assert not non_tty_bar._active

    def test_deactivate_noop_when_not_active(self, non_tty_bar):
        non_tty_bar.deactivate()  # should not raise
        assert not non_tty_bar._active

    @patch("os.get_terminal_size")
    @patch("signal.getsignal")
    @patch("signal.signal")
    def test_double_activate_is_idempotent(
        self, mock_signal, mock_getsignal, mock_termsize, bar
    ):
        mock_termsize.return_value = os.terminal_size((80, 24))
        mock_getsignal.return_value = None

        bar.activate()
        bar.activate()  # second call should be no-op
        assert bar._active is True


class TestAnsiOutput:
    @patch("os.get_terminal_size")
    @patch("signal.getsignal")
    @patch("signal.signal")
    def test_activate_writes_scroll_region_escape(
        self, mock_signal, mock_getsignal, mock_termsize, bar, capsys
    ):
        mock_termsize.return_value = os.terminal_size((80, 24))
        mock_getsignal.return_value = None

        bar.activate()
        output = capsys.readouterr().out

        # Should contain DECSTBM scroll region: \033[1;21r (24 - 3 = 21)
        expected_scroll = "\033[1;21r"
        assert expected_scroll in output

    @patch("os.get_terminal_size")
    @patch("signal.getsignal")
    @patch("signal.signal")
    def test_deactivate_resets_scroll_region(
        self, mock_signal, mock_getsignal, mock_termsize, bar, capsys
    ):
        mock_termsize.return_value = os.terminal_size((80, 24))
        mock_getsignal.return_value = None

        bar.activate()
        capsys.readouterr()  # discard activate output

        bar.deactivate()
        output = capsys.readouterr().out

        # Should reset scroll region to full terminal: \033[1;24r
        expected_reset = "\033[1;24r"
        assert expected_reset in output


class TestBottomToolbar:
    def test_toolbar_text_contains_mode(self, bar):
        text = bar.get_bottom_toolbar_text()
        assert "cadforge:agent&gt;" in text

    def test_toolbar_text_contains_hints(self, bar):
        text = bar.get_bottom_toolbar_text()
        assert "Shift+Tab" in text
        assert "Ctrl+C" in text
        assert "/help" in text

    def test_toolbar_text_reflects_mode_change(self, bar):
        bar.set_mode("PLAN", "yellow")
        text = bar.get_bottom_toolbar_text()
        assert "cadforge:plan&gt;" in text
        assert "ansiyellow" in text


class TestDraw:
    @patch("os.get_terminal_size")
    @patch("signal.getsignal")
    @patch("signal.signal")
    def test_draw_includes_box_drawing_chars(
        self, mock_signal, mock_getsignal, mock_termsize, bar, capsys
    ):
        mock_termsize.return_value = os.terminal_size((80, 24))
        mock_getsignal.return_value = None

        bar.activate()
        output = capsys.readouterr().out

        # Box drawing characters should be present
        assert "\u250c" in output  # top-left
        assert "\u2510" in output  # top-right
        assert "\u2514" in output  # bottom-left
        assert "\u2518" in output  # bottom-right
        assert "\u2502" in output  # vertical

    @patch("os.get_terminal_size")
    @patch("signal.getsignal")
    @patch("signal.signal")
    def test_draw_shows_busy_status(
        self, mock_signal, mock_getsignal, mock_termsize, bar, capsys
    ):
        mock_termsize.return_value = os.terminal_size((80, 24))
        mock_getsignal.return_value = None

        bar.activate()
        capsys.readouterr()  # discard activate output

        bar.set_busy("Executing Bash...")
        output = capsys.readouterr().out
        assert "Executing Bash..." in output
