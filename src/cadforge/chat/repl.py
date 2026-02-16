"""prompt_toolkit REPL for CadForge chat interface."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from cadforge.chat.modes import InteractionMode
from cadforge.chat.renderer import ChatRenderer
from cadforge.config import load_settings, save_settings
from cadforge.core.agent import Agent
from cadforge.core.session import Session
from cadforge.skills.loader import discover_skills, get_skill_by_name
from cadforge.utils.paths import get_project_settings_path


def run_repl(
    project_root: Path,
    session_id: str | None = None,
) -> None:
    """Run the interactive REPL chat loop.

    Args:
        project_root: Project root directory
        session_id: Optional session ID to resume
    """
    renderer = ChatRenderer()
    settings = load_settings(project_root)

    # Set up session
    session = Session(project_root, session_id)
    if session_id:
        session.load()
        renderer.render_info(f"Resumed session: {session_id}")

    # Set up agent with styled permission prompt
    def ask_callback(prompt: str) -> bool:
        try:
            renderer.render_tool_permission(prompt)
            try:
                from prompt_toolkit import prompt as pt_prompt
                from prompt_toolkit.formatted_text import HTML

                response = pt_prompt(HTML('<style fg="yellow">[Y/n] </style>')).strip().lower()
            except ImportError:
                response = input("[Y/n] ").strip().lower()
            return response in ("", "y", "yes")
        except (EOFError, KeyboardInterrupt):
            return False

    agent = Agent(
        project_root=project_root,
        settings=settings,
        session=session,
        ask_callback=ask_callback,
        output_callback=lambda text: renderer.render_assistant_message(text),
    )

    mode = InteractionMode.AGENT
    renderer.render_welcome(mode.display_name, mode.color)

    # Show auth status
    if settings.provider == "ollama":
        base_url = settings.base_url or "http://localhost:11434/v1"
        renderer.render_info(f"Provider: Ollama (local) — {settings.model} @ {base_url}")
    else:
        auth_labels = {
            "api_key": "API key",
            "env_token": "ANTHROPIC_AUTH_TOKEN",
            "claude_code": "Claude Code OAuth (subscription)",
            "none": "No credentials found",
        }
        auth_label = auth_labels.get(agent._auth_creds.source, agent._auth_creds.source)
        if agent._auth_creds.is_valid:
            renderer.render_info(f"Auth: {auth_label}")
        else:
            renderer.render_error(
                "No authentication configured. Set ANTHROPIC_API_KEY, "
                "ANTHROPIC_AUTH_TOKEN, or log in to Claude Code."
            )

    # Discover available skills
    skills = discover_skills(project_root)
    slash_commands = {f"/{s.name}": s for s in skills}

    try:
        _repl_loop(agent, renderer, slash_commands, project_root, mode)
    except KeyboardInterrupt:
        pass
    finally:
        agent.save_session()
        renderer.render_info("Session saved.")


def _repl_loop(
    agent: Agent,
    renderer: ChatRenderer,
    slash_commands: dict,
    project_root: Path,
    mode: InteractionMode,
) -> None:
    """Main REPL input loop."""
    try:
        from prompt_toolkit import PromptSession
        from prompt_toolkit.formatted_text import HTML
        from prompt_toolkit.history import FileHistory
        from prompt_toolkit.key_binding import KeyBindings
        from prompt_toolkit.keys import Keys

        has_prompt_toolkit = True
    except ImportError:
        has_prompt_toolkit = False

    if has_prompt_toolkit:
        bindings = KeyBindings()

        @bindings.add(Keys.BackTab)  # Shift+Tab
        def _cycle_mode(event):
            nonlocal mode
            mode = mode.next()
            renderer.render_mode_change(mode.display_name, mode.color)

        @bindings.add("c-l")  # Ctrl+L
        def _clear_screen(event):
            event.app.renderer.clear()

        history_path = project_root / ".cadforge" / "history"
        prompt_session = PromptSession(
            history=FileHistory(str(history_path)),
            key_bindings=bindings,
        )

        def get_prompt():
            return HTML(f'<style fg="{mode.color}">cadforge:{mode.value}&gt; </style>')

        def get_input():
            return prompt_session.prompt(get_prompt)
    else:
        def get_input():
            return input(f"cadforge:{mode.value}> ")

    while True:
        try:
            raw_input = get_input().strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if not raw_input:
            continue

        # Multi-line via backslash continuation
        user_input = _handle_continuation(raw_input, get_input)

        # Shell shortcut: !command
        if user_input.startswith("!"):
            _handle_shell_command(user_input[1:], renderer, project_root)
            continue

        # Handle built-in commands
        if user_input == "/quit" or user_input == "/exit":
            break
        elif user_input == "/help":
            _show_help(renderer, slash_commands, mode)
            continue
        elif user_input == "/skills":
            _show_skills(renderer, slash_commands)
            continue
        elif user_input == "/sessions":
            _show_sessions(renderer, agent)
            continue
        elif user_input.startswith("/provider"):
            _handle_provider(user_input, agent, renderer, project_root)
            continue
        elif user_input == "/agent":
            mode = InteractionMode.AGENT
            renderer.render_mode_change(mode.display_name, mode.color)
            continue
        elif user_input == "/plan":
            mode = InteractionMode.PLAN
            renderer.render_mode_change(mode.display_name, mode.color)
            continue
        elif user_input == "/ask":
            mode = InteractionMode.ASK
            renderer.render_mode_change(mode.display_name, mode.color)
            continue
        elif user_input == "/mode":
            renderer.render_mode_change(mode.display_name, mode.color)
            continue

        # Handle slash commands (skills)
        parts = user_input.split(None, 1)
        cmd = parts[0]
        if cmd in slash_commands:
            skill = slash_commands[cmd]
            skill_arg = parts[1] if len(parts) > 1 else ""
            user_input = f"{skill.prompt}\n\nUser request: {skill_arg}"

        # Process through agent with current mode
        response = agent.process_message(user_input, mode=mode.value)
        renderer.render_assistant_message(response)


def _handle_continuation(raw_input: str, get_input) -> str:
    """Handle backslash continuation for multi-line input."""
    lines = [raw_input]
    while lines[-1].endswith("\\"):
        lines[-1] = lines[-1][:-1]
        try:
            lines.append(get_input())
        except (EOFError, KeyboardInterrupt):
            break
    return "\n".join(lines)


def _handle_shell_command(command: str, renderer: ChatRenderer, project_root: Path) -> None:
    """Execute a shell command directly."""
    command = command.strip()
    if not command:
        renderer.render_info("Usage: !<command>")
        return
    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            cwd=str(project_root),
            timeout=120,
        )
        if result.stdout:
            renderer.render_info(result.stdout.rstrip())
        if result.stderr:
            renderer.render_error(result.stderr.rstrip())
    except subprocess.TimeoutExpired:
        renderer.render_error("Command timed out after 120 seconds.")
    except Exception as e:
        renderer.render_error(f"Shell error: {e}")


def _show_help(renderer: ChatRenderer, slash_commands: dict, mode: InteractionMode) -> None:
    """Show help message with mode info and keyboard shortcuts."""
    help_text = (
        f"**Current Mode:** {mode.display_name}\n\n"
        "**Modes:**\n"
        "- `/agent` — Full agentic loop with all tools\n"
        "- `/plan` — Read-only, generates plans without modifying files\n"
        "- `/ask` — Pure Q&A, no tools, answers from knowledge\n"
        "- `/mode` — Show current mode\n\n"
        "**Commands:**\n"
        "- `/help` — Show this help\n"
        "- `/provider` — Show or switch LLM provider\n"
        "- `/skills` — List available skills\n"
        "- `/sessions` — List recent sessions\n"
        "- `/quit` — Exit CadForge\n\n"
        "**Shortcuts:**\n"
        "- `Shift+Tab` — Cycle modes (agent -> plan -> ask)\n"
        "- `Ctrl+L` — Clear screen\n"
        "- `!command` — Run shell command directly\n"
        "- `\\` at end of line — Continue on next line\n"
    )
    if slash_commands:
        help_text += "\n**Skills:**\n"
        for cmd, skill in slash_commands.items():
            help_text += f"- `{cmd}` — {skill.description}\n"

    renderer.render_assistant_message(help_text)


def _show_skills(renderer: ChatRenderer, slash_commands: dict) -> None:
    """Show available skills."""
    if not slash_commands:
        renderer.render_info("No skills found.")
        return
    for cmd, skill in slash_commands.items():
        renderer.render_info(f"  {cmd} — {skill.description}")


def _show_sessions(renderer: ChatRenderer, agent: Agent) -> None:
    """Show recent sessions."""
    sessions = agent.session_index.list_sessions(limit=10)
    if not sessions:
        renderer.render_info("No previous sessions found.")
        return
    for s in sessions:
        renderer.render_info(f"  {s.session_id}: {s.summary} ({s.message_count} msgs)")


def _handle_provider(
    user_input: str,
    agent: Agent,
    renderer: ChatRenderer,
    project_root: Path,
) -> None:
    """Handle the /provider command."""
    parts = user_input.split()

    # /provider — show current
    if len(parts) == 1:
        base_url = agent.settings.base_url or ""
        if agent.settings.provider == "ollama":
            base_url = agent.settings.base_url or "http://localhost:11434/v1"
            renderer.render_info(
                f"Provider: {agent.settings.provider}  Model: {agent.settings.model}  URL: {base_url}"
            )
        else:
            renderer.render_info(
                f"Provider: {agent.settings.provider}  Model: {agent.settings.model}"
            )
        return

    new_provider = parts[1]
    if new_provider not in ("anthropic", "ollama"):
        renderer.render_error(f"Unknown provider: {new_provider}. Use 'anthropic' or 'ollama'.")
        return

    new_model = parts[2] if len(parts) >= 3 else None

    agent.settings.provider = new_provider
    if new_model:
        agent.settings.model = new_model

    # Set sensible defaults when switching providers
    if new_provider == "ollama":
        if not new_model:
            agent.settings.model = "qwen2.5-coder:14b"
        if not agent.settings.base_url:
            agent.settings.base_url = "http://localhost:11434/v1"
    elif new_provider == "anthropic":
        if not new_model:
            agent.settings.model = "claude-sonnet-4-5-20250929"
        agent.settings.base_url = None

    agent.update_provider()

    # Persist to project settings
    settings_path = get_project_settings_path(project_root)
    save_settings(agent.settings, settings_path)

    if new_provider == "ollama":
        renderer.render_info(
            f"Switched to {new_provider} — {agent.settings.model} @ {agent.settings.base_url}"
        )
    else:
        renderer.render_info(f"Switched to {new_provider} — {agent.settings.model}")
