"""Persistent prompt bar using ANSI scroll regions.

Reserves the bottom 3 lines of the terminal for a fixed bar showing
the current mode, status, and keyboard hints.  All stdout output
(Rich panels, streaming text) is confined to the scroll region above.

IDLE state: deactivate() restores full terminal so prompt_toolkit can
            render its own bottom_toolbar with the same visual bar.
BUSY state: activate() constrains output, draws the bar with status text.
"""

from __future__ import annotations

import io
import os
import signal
import sys
from typing import Callable


# Number of terminal rows reserved for the bar (border + status + border)
BAR_HEIGHT = 3


class PromptBar:
    """Manages a persistent 3-line bar at the bottom of the terminal."""

    def __init__(self) -> None:
        self._active = False
        self._mode_label = "AGENT"
        self._mode_color_code = "32"  # green
        self._status_text = ""
        self._busy = False
        try:
            self._is_tty = os.isatty(sys.stdout.fileno())
        except (AttributeError, OSError, io.UnsupportedOperation):
            self._is_tty = False
        self._prev_sigwinch: signal.Handlers | None = None

    # --- ANSI color codes for mode colors ---

    _COLOR_MAP: dict[str, str] = {
        "green": "32",
        "yellow": "33",
        "cyan": "36",
        "red": "31",
        "blue": "34",
    }

    # --- Public API ---

    def activate(self) -> None:
        """Set scroll region to reserve bottom 3 lines and draw the bar."""
        if not self._is_tty or self._active:
            return
        self._active = True
        h = self._height()
        # Set scroll region: rows 1..(H - BAR_HEIGHT)
        scroll_bottom = h - BAR_HEIGHT
        sys.stdout.write(f"\033[1;{scroll_bottom}r")
        # Move cursor to top of scroll region
        sys.stdout.write(f"\033[{scroll_bottom};1H")
        sys.stdout.flush()
        # Install SIGWINCH handler
        try:
            self._prev_sigwinch = signal.getsignal(signal.SIGWINCH)
            signal.signal(signal.SIGWINCH, self._on_resize)
        except (OSError, ValueError):
            pass
        self.draw()

    def deactivate(self) -> None:
        """Reset scroll region to full terminal and clear bar lines."""
        if not self._is_tty or not self._active:
            return
        self._active = False
        h = self._height()
        # Reset scroll region to full terminal
        sys.stdout.write(f"\033[1;{h}r")
        # Clear the bar lines
        for row in range(h - BAR_HEIGHT + 1, h + 1):
            sys.stdout.write(f"\033[{row};1H\033[2K")
        # Move cursor back to just above where bar was
        sys.stdout.write(f"\033[{h - BAR_HEIGHT};1H")
        sys.stdout.flush()
        # Restore SIGWINCH handler
        if self._prev_sigwinch is not None:
            try:
                signal.signal(signal.SIGWINCH, self._prev_sigwinch)
            except (OSError, ValueError):
                pass
            self._prev_sigwinch = None

    def draw(self) -> None:
        """Draw the 3-line bar in the reserved area."""
        if not self._is_tty or not self._active:
            return
        h = self._height()
        w = self._width()
        bar_top = h - BAR_HEIGHT + 1  # first bar row

        # Save cursor
        sys.stdout.write("\0337")

        # --- Row 1: top border ---
        border_line = "\u2500" * (w - 2)
        sys.stdout.write(f"\033[{bar_top};1H\033[2K")
        sys.stdout.write(f"\u250c{border_line}\u2510")

        # --- Row 2: input/status line ---
        if self._busy:
            content = f" cadforge:{self._mode_label.lower()}> {self._status_text}"
        else:
            content = f" cadforge:{self._mode_label.lower()}>"
        # Pad to width, truncate if needed
        content = content[:w - 4]
        padding = w - 2 - len(content)
        sys.stdout.write(f"\033[{bar_top + 1};1H\033[2K")
        sys.stdout.write(
            f"\u2502\033[{self._mode_color_code}m{content}\033[0m"
            f"{' ' * padding}\u2502"
        )

        # --- Row 3: bottom border with hints ---
        hints = " Shift+Tab: mode \u2502 Ctrl+C: cancel \u2502 /help "
        # Center hints in border
        border_left_len = (w - 2 - len(hints)) // 2
        border_right_len = w - 2 - len(hints) - border_left_len
        if border_left_len < 0:
            # Terminal too narrow for hints
            hints = ""
            border_left_len = (w - 2) // 2
            border_right_len = w - 2 - border_left_len
        sys.stdout.write(f"\033[{bar_top + 2};1H\033[2K")
        left_border = "\u2500" * border_left_len
        right_border = "\u2500" * border_right_len
        sys.stdout.write(
            f"\u2514{left_border}{hints}"
            f"{right_border}\u2518"
        )

        # Restore cursor
        sys.stdout.write("\0338")
        sys.stdout.flush()

    def set_mode(self, mode_name: str, color: str) -> None:
        """Update the mode label and color, then redraw."""
        self._mode_label = mode_name
        self._mode_color_code = self._COLOR_MAP.get(color, "32")
        self.draw()

    def set_busy(self, status: str = "Thinking...") -> None:
        """Switch to busy state with a status message."""
        self._busy = True
        self._status_text = status
        self.draw()

    def set_idle(self) -> None:
        """Switch back to idle state."""
        self._busy = False
        self._status_text = ""
        self.draw()

    def update_status(self, text: str) -> None:
        """Update the status text displayed in the bar."""
        self._status_text = text
        self.draw()

    def get_bottom_toolbar_text(self) -> str:
        """Return HTML-formatted text for prompt_toolkit bottom_toolbar.

        Used during IDLE state when prompt_toolkit owns the terminal.
        Returns markup matching the visual appearance of the active bar.
        """
        hints = "Shift+Tab: mode │ Ctrl+C: cancel │ /help"
        return (
            f'<style bg="ansiblack" fg="ansiwhite">'
            f' <style fg="ansi{self._mode_color_name()}">'
            f"cadforge:{self._mode_label.lower()}&gt;</style>"
            f"  {hints} </style>"
        )

    # --- Internal helpers ---

    def _mode_color_name(self) -> str:
        """Reverse map ANSI code to color name for prompt_toolkit."""
        reverse = {v: k for k, v in self._COLOR_MAP.items()}
        return reverse.get(self._mode_color_code, "green")

    def _height(self) -> int:
        try:
            return os.get_terminal_size().lines
        except (OSError, ValueError):
            return 24

    def _width(self) -> int:
        try:
            return os.get_terminal_size().columns
        except (OSError, ValueError):
            return 80

    def _on_resize(self, sig: int, frame: object) -> None:
        """Handle terminal resize: recalculate scroll region and redraw."""
        if not self._active:
            return
        h = self._height()
        scroll_bottom = h - BAR_HEIGHT
        sys.stdout.write(f"\033[1;{scroll_bottom}r")
        sys.stdout.flush()
        self.draw()
        # Chain to previous handler if any
        if self._prev_sigwinch and callable(self._prev_sigwinch):
            self._prev_sigwinch(sig, frame)
