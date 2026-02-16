"""prompt_toolkit REPL for CadForge chat interface."""

from __future__ import annotations

from pathlib import Path
from typing import Any

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

    # Set up agent
    def ask_callback(prompt: str) -> bool:
        try:
            response = input(prompt).strip().lower()
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

    renderer.render_welcome()

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
        _repl_loop(agent, renderer, slash_commands, project_root)
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
) -> None:
    """Main REPL input loop."""
    try:
        from prompt_toolkit import PromptSession
        from prompt_toolkit.history import FileHistory

        history_path = project_root / ".cadforge" / "history"
        prompt_session = PromptSession(
            history=FileHistory(str(history_path)),
        )
        get_input = lambda: prompt_session.prompt("cadforge> ")
    except ImportError:
        get_input = lambda: input("cadforge> ")

    while True:
        try:
            user_input = get_input().strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if not user_input:
            continue

        # Handle built-in commands
        if user_input == "/quit" or user_input == "/exit":
            break
        elif user_input == "/help":
            _show_help(renderer, slash_commands)
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

        # Handle slash commands (skills)
        parts = user_input.split(None, 1)
        cmd = parts[0]
        if cmd in slash_commands:
            skill = slash_commands[cmd]
            skill_arg = parts[1] if len(parts) > 1 else ""
            user_input = f"{skill.prompt}\n\nUser request: {skill_arg}"

        # Process through agent
        response = agent.process_message(user_input)
        renderer.render_assistant_message(response)


def _show_help(renderer: ChatRenderer, slash_commands: dict) -> None:
    """Show help message."""
    help_text = (
        "**Commands:**\n"
        "- `/help` — Show this help\n"
        "- `/provider` — Show or switch LLM provider\n"
        "- `/skills` — List available skills\n"
        "- `/sessions` — List recent sessions\n"
        "- `/quit` — Exit CadForge\n"
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
