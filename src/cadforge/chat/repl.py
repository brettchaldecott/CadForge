"""prompt_toolkit REPL for CadForge chat interface.

The REPL is the supervisor: the agent runs as a cancellable asyncio.Task.
Ctrl+C and Escape cancel the running agent and return to the prompt.
"""

from __future__ import annotations

import asyncio
import os
import signal
import subprocess
import sys
from pathlib import Path
from typing import Any

from cadforge.chat.modes import InteractionMode
from cadforge.chat.prompt_bar import PromptBar
from cadforge.chat.renderer import ChatRenderer
from cadforge.config import load_settings, save_settings
from cadforge.core.agent import Agent
from cadforge.core.events import AgentEvent, EventType
from cadforge.core.session import Session
from cadforge.skills.loader import discover_skills, get_skill_by_name
from cadforge.utils.paths import get_project_settings_path


def run_repl(
    project_root: Path,
    session_id: str | None = None,
) -> None:
    """Run the interactive REPL chat loop.

    Entry point that sets up the session/agent then hands off to the
    async event loop.  Falls back to the sync loop if asyncio setup fails.
    """
    prompt_bar = PromptBar()
    renderer = ChatRenderer(prompt_bar=prompt_bar)
    settings = load_settings(project_root)

    # Set up session
    session = Session(project_root, session_id)
    if session_id:
        session.load()
        renderer.render_info(f"Resumed session: {session_id}")

    # Permission prompt callback — used by both sync and async paths.
    # During async execution the agent task is suspended at an await point
    # while the permission prompt runs in a thread via to_thread(), so
    # stdin is free.
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
        asyncio.run(_async_repl(agent, renderer, slash_commands, project_root, mode, prompt_bar))
    except KeyboardInterrupt:
        pass
    finally:
        prompt_bar.deactivate()
        agent.save_session()
        renderer.render_info("Session saved.")


# ---------------------------------------------------------------------------
# Async REPL
# ---------------------------------------------------------------------------

async def _async_repl(
    agent: Agent,
    renderer: ChatRenderer,
    slash_commands: dict,
    project_root: Path,
    mode: InteractionMode,
    prompt_bar: PromptBar | None = None,
) -> None:
    """Async REPL loop using prompt_toolkit's prompt_async."""
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
            if prompt_bar:
                prompt_bar.set_mode(mode.display_name, mode.color)
            renderer.render_mode_change(mode.display_name, mode.color)

        @bindings.add("c-l")  # Ctrl+L
        def _clear_screen(event):
            event.app.renderer.clear()

        history_path = project_root / ".cadforge" / "history"
        history_path.parent.mkdir(parents=True, exist_ok=True)

        def get_toolbar():
            if prompt_bar:
                return HTML(prompt_bar.get_bottom_toolbar_text())
            return None

        prompt_session = PromptSession(
            history=FileHistory(str(history_path)),
            key_bindings=bindings,
            bottom_toolbar=get_toolbar,
        )

        def get_prompt():
            return HTML(f'<style fg="{mode.color}">cadforge:{mode.value}&gt; </style>')

        async def get_input():
            if prompt_bar:
                prompt_bar.deactivate()
            return await prompt_session.prompt_async(get_prompt)
    else:
        async def get_input():
            return await asyncio.to_thread(input, f"cadforge:{mode.value}> ")

    while True:
        try:
            raw_input = (await get_input()).strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if not raw_input:
            continue

        # Multi-line via backslash continuation
        user_input = await _handle_continuation_async(raw_input, get_input)

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
            if prompt_bar:
                prompt_bar.set_mode(mode.display_name, mode.color)
            renderer.render_mode_change(mode.display_name, mode.color)
            continue
        elif user_input == "/plan":
            mode = InteractionMode.PLAN
            if prompt_bar:
                prompt_bar.set_mode(mode.display_name, mode.color)
            renderer.render_mode_change(mode.display_name, mode.color)
            continue
        elif user_input == "/ask":
            mode = InteractionMode.ASK
            if prompt_bar:
                prompt_bar.set_mode(mode.display_name, mode.color)
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

        # Activate prompt bar before agent runs
        if prompt_bar:
            prompt_bar.activate()

        # Process through async agent with streaming
        await _run_agent_with_events(agent, renderer, user_input, mode)


# ---------------------------------------------------------------------------
# Agent execution with event-driven rendering
# ---------------------------------------------------------------------------

async def _run_agent_with_events(
    agent: Agent,
    renderer: ChatRenderer,
    user_input: str,
    mode: InteractionMode,
) -> None:
    """Run agent as a cancellable task, consuming events for rendering.

    Ctrl+C cancels the agent and returns to the prompt.
    Escape during execution also cancels.
    """
    event_queue: asyncio.Queue[AgentEvent] = asyncio.Queue()

    # Drain any pending stdin data (e.g. CPR responses from prompt_toolkit)
    # before starting the escape listener, so stale escape sequences are
    # not mistaken for a bare Escape keypress.
    _drain_stdin()

    agent_task = asyncio.create_task(
        agent.process_message_async(user_input, mode=mode.value, event_queue=event_queue)
    )

    # --- Escape key listener ---
    escape_task = asyncio.create_task(_wait_for_escape())

    # --- SIGINT handler (Ctrl+C) ---
    loop = asyncio.get_running_loop()
    original_handler = signal.getsignal(signal.SIGINT)

    def _sigint_cancel(sig, frame):
        agent_task.cancel()

    signal.signal(signal.SIGINT, _sigint_cancel)

    streaming_started = False
    try:
        while not agent_task.done():
            # Wait for either an event, escape, or agent completion
            get_event = asyncio.ensure_future(_safe_queue_get(event_queue, timeout=0.1))
            done, pending = await asyncio.wait(
                [get_event, escape_task, agent_task],
                return_when=asyncio.FIRST_COMPLETED,
            )

            # Cancel pending futures we don't need
            if get_event in pending:
                get_event.cancel()

            # Check if escape was pressed
            if escape_task in done:
                agent_task.cancel()
                try:
                    await agent_task
                except asyncio.CancelledError:
                    pass
                break

            # Process event if we got one
            if get_event in done:
                try:
                    event = get_event.result()
                except (asyncio.TimeoutError, asyncio.CancelledError):
                    continue
                if event is not None:
                    if not streaming_started:
                        renderer.render_streaming_start()
                        streaming_started = True
                    _handle_event(event, renderer)
                    if event.type in (EventType.COMPLETION, EventType.CANCELLED, EventType.ERROR):
                        break

        # Drain remaining events from the queue
        while not event_queue.empty():
            try:
                event = event_queue.get_nowait()
                if not streaming_started:
                    renderer.render_streaming_start()
                    streaming_started = True
                _handle_event(event, renderer)
            except asyncio.QueueEmpty:
                break

        # Await agent task to propagate exceptions
        if not agent_task.done():
            try:
                await agent_task
            except asyncio.CancelledError:
                if not streaming_started:
                    renderer.render_streaming_start()
                renderer.render_cancelled()

    except asyncio.CancelledError:
        if not streaming_started:
            renderer.render_streaming_start()
        renderer.render_cancelled()
    finally:
        # Restore signal handler
        signal.signal(signal.SIGINT, original_handler)
        # Clean up escape task
        if not escape_task.done():
            escape_task.cancel()
            try:
                await escape_task
            except asyncio.CancelledError:
                pass
        if streaming_started:
            renderer.render_streaming_end()


async def _safe_queue_get(
    queue: asyncio.Queue[AgentEvent],
    timeout: float = 0.1,
) -> AgentEvent | None:
    """Get from queue with timeout, returning None on timeout."""
    try:
        return await asyncio.wait_for(queue.get(), timeout=timeout)
    except asyncio.TimeoutError:
        return None


def _drain_stdin() -> None:
    """Drain any pending data on stdin (non-blocking).

    This flushes stale escape sequences (e.g. CPR responses from
    prompt_toolkit) so the escape listener doesn't misinterpret them.
    """
    try:
        import select
        import termios
        import tty
    except ImportError:
        return

    fd = sys.stdin.fileno()
    try:
        old_settings = termios.tcgetattr(fd)
        tty.setcbreak(fd)
        try:
            while select.select([fd], [], [], 0)[0]:
                os.read(fd, 1024)
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
    except (OSError, termios.error):
        pass


async def _wait_for_escape() -> None:
    """Wait for the Escape key to be pressed.

    Reads stdin char-by-char in a thread executor. Returns when a
    bare Escape (0x1b) is detected — i.e. ESC not followed immediately
    by ``[`` (which would indicate a CSI escape sequence such as a
    cursor-position report from the terminal).

    On platforms without termios (Windows) this awaits forever
    (Escape cancellation is not supported there).
    """
    try:
        import select
        import termios
        import tty
    except ImportError:
        # termios not available (e.g. Windows) — just wait forever
        await asyncio.Event().wait()
        return

    fd = sys.stdin.fileno()

    def _read_escape():
        old_settings = termios.tcgetattr(fd)
        try:
            tty.setcbreak(fd)
            while True:
                ch = sys.stdin.read(1)
                if ch == "\x1b":
                    # Check if more data follows within 50ms.
                    # If so, this is an escape *sequence* (e.g. CSI),
                    # not a bare ESC keypress.
                    ready, _, _ = select.select([fd], [], [], 0.05)
                    if ready:
                        next_ch = sys.stdin.read(1)
                        if next_ch == "[":
                            # CSI sequence — consume until final byte
                            while True:
                                c = sys.stdin.read(1)
                                if c.isalpha() or c == "~":
                                    break
                        # SS2/SS3 or other multi-byte — consumed, continue
                        continue
                    # No followup — bare Escape key
                    return
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)

    try:
        await asyncio.to_thread(_read_escape)
    except (OSError, asyncio.CancelledError):
        pass


def _handle_event(event: AgentEvent, renderer: ChatRenderer) -> None:
    """Dispatch an agent event to the appropriate renderer method."""
    if event.type == EventType.TEXT_DELTA:
        renderer.render_text_delta(event.data.get("text", ""))
    elif event.type == EventType.TEXT_DONE:
        renderer.render_text_done()
    elif event.type == EventType.TOOL_USE_START:
        renderer.render_tool_use(event.data.get("name", ""), {})
    elif event.type == EventType.TOOL_RESULT:
        result = event.data.get("result", {})
        renderer.render_tool_result(event.data.get("name", ""), result)
    elif event.type == EventType.STATUS:
        renderer.render_status(event.data.get("message", ""))
    elif event.type == EventType.COMPLETION:
        pass  # Text was already streamed via TEXT_DELTA events
    elif event.type == EventType.CANCELLED:
        renderer.render_cancelled()
    elif event.type == EventType.ERROR:
        renderer.render_error(event.data.get("message", "Unknown error"))


# ---------------------------------------------------------------------------
# Async multi-line continuation
# ---------------------------------------------------------------------------

async def _handle_continuation_async(raw_input: str, get_input) -> str:
    """Handle backslash continuation for multi-line input (async)."""
    lines = [raw_input]
    while lines[-1].endswith("\\"):
        lines[-1] = lines[-1][:-1]
        try:
            lines.append(await get_input())
        except (EOFError, KeyboardInterrupt):
            break
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Helper functions (unchanged from sync version)
# ---------------------------------------------------------------------------

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
        "- `Ctrl+C` / `Escape` — Cancel running agent\n"
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
