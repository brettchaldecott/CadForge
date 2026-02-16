"""Rich terminal rendering for CadForge chat output."""

from __future__ import annotations

import sys
from typing import Any

try:
    from rich.console import Console
    from rich.markdown import Markdown
    from rich.panel import Panel
    from rich.syntax import Syntax
    from rich.text import Text

    HAS_RICH = True
except ImportError:
    HAS_RICH = False


class ChatRenderer:
    """Renders chat output with rich formatting."""

    def __init__(self, use_rich: bool = True):
        self.use_rich = use_rich and HAS_RICH
        if self.use_rich:
            self.console = Console()
        else:
            self.console = None

    def render_assistant_message(self, text: str) -> None:
        """Render an assistant response."""
        if self.use_rich:
            self.console.print()
            self.console.print(Markdown(text))
            self.console.print()
        else:
            print(f"\n{text}\n")

    def render_tool_use(self, tool_name: str, tool_input: dict[str, Any]) -> None:
        """Render a tool use notification."""
        if self.use_rich:
            self.console.print(
                Panel(
                    f"[bold]{tool_name}[/bold]",
                    title="Tool Use",
                    border_style="blue",
                    expand=False,
                )
            )
        else:
            print(f"[Tool: {tool_name}]")

    def render_tool_result(self, tool_name: str, result: dict[str, Any]) -> None:
        """Render a tool execution result."""
        success = result.get("success", False)
        if self.use_rich:
            style = "green" if success else "red"
            status = "OK" if success else "FAIL"
            self.console.print(f"  [{style}]{status}[/{style}]", end=" ")
            if error := result.get("error"):
                self.console.print(f"[red]{error}[/red]")
            elif path := result.get("output_path"):
                self.console.print(f"[dim]{path}[/dim]")
            else:
                self.console.print()
        else:
            status = "OK" if success else "FAIL"
            print(f"  [{status}]", end=" ")
            if error := result.get("error"):
                print(error)
            else:
                print()

    def render_error(self, message: str) -> None:
        """Render an error message."""
        if self.use_rich:
            self.console.print(f"[bold red]Error:[/bold red] {message}")
        else:
            print(f"Error: {message}")

    def render_info(self, message: str) -> None:
        """Render an informational message."""
        if self.use_rich:
            self.console.print(f"[dim]{message}[/dim]")
        else:
            print(message)

    def render_code(self, code: str, language: str = "python") -> None:
        """Render a code block."""
        if self.use_rich:
            self.console.print(Syntax(code, language, theme="monokai"))
        else:
            print(code)

    def render_tool_permission(self, prompt: str) -> None:
        """Render a styled tool permission request."""
        if self.use_rich:
            self.console.print(
                Panel(
                    prompt,
                    title="Permission Required",
                    border_style="yellow",
                    expand=False,
                )
            )
        else:
            print(f"[Permission] {prompt}")

    def render_mode_change(self, mode_name: str, color: str) -> None:
        """Render a mode change notification."""
        if self.use_rich:
            self.console.print(
                f"[bold {color}]Mode: {mode_name}[/bold {color}]"
            )
        else:
            print(f"Mode: {mode_name}")

    def render_welcome(self, mode_name: str = "AGENT", mode_color: str = "green") -> None:
        """Render the welcome message with current mode."""
        if self.use_rich:
            self.console.print(
                Panel(
                    "[bold]CadForge[/bold] — AI-powered CAD for 3D printing\n"
                    f"Mode: [{mode_color}]{mode_name}[/{mode_color}]  "
                    "Shift+Tab: cycle modes  /help: commands",
                    border_style="cyan",
                )
            )
        else:
            print(f"CadForge — AI-powered CAD for 3D printing  [Mode: {mode_name}]")
            print("Shift+Tab: cycle modes  /help: commands")
            print()

    # --- Streaming render methods ---

    def render_streaming_start(self) -> None:
        """Called before the first streamed token."""
        if self.use_rich:
            self.console.print()
        else:
            print()

    def render_text_delta(self, text: str) -> None:
        """Print a streamed token without newline."""
        sys.stdout.write(text)
        sys.stdout.flush()

    def render_text_done(self) -> None:
        """End of a text content block — print newline."""
        sys.stdout.write("\n")
        sys.stdout.flush()

    def render_status(self, message: str) -> None:
        """Show a transient status message (overwritten by next output)."""
        if self.use_rich:
            self.console.print(f"[dim italic]{message}[/dim italic]", end="\r")
        else:
            sys.stdout.write(f"\r{message}")
            sys.stdout.flush()

    def render_cancelled(self) -> None:
        """Show cancellation notice."""
        if self.use_rich:
            self.console.print("\n[bold yellow]Cancelled.[/bold yellow]")
        else:
            print("\nCancelled.")

    def render_streaming_end(self) -> None:
        """Called after streaming is complete."""
        if self.use_rich:
            self.console.print()
        else:
            print()
