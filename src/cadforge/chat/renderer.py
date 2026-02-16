"""Rich terminal rendering for CadForge chat output."""

from __future__ import annotations

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

    def render_welcome(self) -> None:
        """Render the welcome message."""
        if self.use_rich:
            self.console.print(
                Panel(
                    "[bold]CadForge[/bold] — AI-powered CAD for 3D printing\n"
                    "Type your request or use /help for commands.",
                    border_style="cyan",
                )
            )
        else:
            print("CadForge — AI-powered CAD for 3D printing")
            print("Type your request or use /help for commands.")
            print()
