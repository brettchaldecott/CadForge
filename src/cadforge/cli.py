"""CadForge CLI — main entry point.

Commands:
  chat      Start interactive chat session
  init      Initialize a new CadForge project
  index     Index the knowledge vault
  view      Preview an STL file
  resume    Resume the last session
  config    View and update project settings
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        prog="cadforge",
        description="CadForge — AI-powered CLI CAD tool for 3D printing",
    )
    subparsers = parser.add_subparsers(dest="command")

    # chat
    chat_parser = subparsers.add_parser("chat", help="Start interactive chat session")
    chat_parser.add_argument("--session", help="Session ID to resume")

    # init
    init_parser = subparsers.add_parser("init", help="Initialize a new CadForge project")
    init_parser.add_argument("path", nargs="?", default=".", help="Project directory")

    # index
    index_parser = subparsers.add_parser("index", help="Index the knowledge vault")
    index_parser.add_argument("--incremental", action="store_true", help="Only re-index changed files")

    # view
    view_parser = subparsers.add_parser("view", help="Preview an STL file")
    view_parser.add_argument("file", help="Path to STL file")

    # resume
    subparsers.add_parser("resume", help="Resume the last session")

    # config
    config_parser = subparsers.add_parser("config", help="View and update project settings")
    config_parser.add_argument(
        "action", choices=["show", "get", "set"], help="Action to perform"
    )
    config_parser.add_argument("key", nargs="?", help="Setting key (for get/set)")
    config_parser.add_argument("value", nargs="?", help="Setting value (for set)")

    args = parser.parse_args(argv)

    if args.command is None:
        # Default to chat if no command given
        args.command = "chat"
        args.session = None

    try:
        if args.command == "chat":
            return cmd_chat(args)
        elif args.command == "init":
            return cmd_init(args)
        elif args.command == "index":
            return cmd_index(args)
        elif args.command == "view":
            return cmd_view(args)
        elif args.command == "resume":
            return cmd_resume(args)
        elif args.command == "config":
            return cmd_config(args)
        else:
            parser.print_help()
            return 1
    except KeyboardInterrupt:
        print("\nInterrupted.")
        return 130
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def cmd_chat(args: argparse.Namespace) -> int:
    """Start interactive chat session."""
    from cadforge.utils.paths import find_project_root
    from cadforge.chat.repl import run_repl

    project_root = find_project_root()
    if project_root is None:
        print("No CadForge project found. Run 'cadforge init' first.", file=sys.stderr)
        return 1

    session_id = getattr(args, "session", None)
    run_repl(project_root, session_id=session_id)
    return 0


def cmd_init(args: argparse.Namespace) -> int:
    """Initialize a new CadForge project."""
    project_dir = Path(args.path).resolve()
    project_dir.mkdir(parents=True, exist_ok=True)

    # Create project structure
    cadforge_dir = project_dir / ".cadforge"
    cadforge_dir.mkdir(exist_ok=True)
    (cadforge_dir / "memory").mkdir(exist_ok=True)

    # CADFORGE.md
    cadforge_md = project_dir / "CADFORGE.md"
    if not cadforge_md.exists():
        cadforge_md.write_text(
            "# CadForge Project\n\n"
            "## Conventions\n"
            "- Add project-specific conventions here\n\n"
            "## Printer\n"
            "<!-- Set your printer: printer: prusa-mk4 -->\n"
        )

    # settings.json
    settings_path = cadforge_dir / "settings.json"
    if not settings_path.exists():
        from cadforge.config import CadForgeSettings, save_settings
        save_settings(CadForgeSettings(), settings_path)

    # MEMORY.md
    memory_md = cadforge_dir / "memory" / "MEMORY.md"
    if not memory_md.exists():
        memory_md.write_text("# Auto-Memory\n\n")

    # Directories
    for d in ["vault", "output", "skills"]:
        (project_dir / d).mkdir(exist_ok=True)

    (project_dir / ".lance").mkdir(exist_ok=True)

    # .gitignore
    gitignore = project_dir / ".gitignore"
    if not gitignore.exists():
        gitignore.write_text(
            "output/\n.lance/\n.cadforge/memory/\n"
            "CADFORGE.local.md\n.cadforge/CADFORGE.local.md\n"
            ".env\nvenv/\n__pycache__/\n"
        )

    print(f"Initialized CadForge project at {project_dir}")
    return 0


def cmd_index(args: argparse.Namespace) -> int:
    """Index the knowledge vault."""
    from cadforge.utils.paths import find_project_root
    from cadforge.vault.indexer import index_vault

    project_root = find_project_root()
    if project_root is None:
        print("No CadForge project found.", file=sys.stderr)
        return 1

    incremental = getattr(args, "incremental", False)
    print(f"Indexing vault {'(incremental)' if incremental else '(full)'}...")
    result = index_vault(project_root, incremental=incremental)

    if result.get("success"):
        print(
            f"Indexed {result['files_indexed']} files, "
            f"{result['chunks_created']} chunks created "
            f"(backend: {result.get('backend', 'unknown')})"
        )
        return 0
    else:
        print(f"Index failed: {result.get('error', 'unknown')}", file=sys.stderr)
        return 1


def cmd_view(args: argparse.Namespace) -> int:
    """Preview an STL file."""
    path = Path(args.file)
    if not path.exists():
        print(f"File not found: {path}", file=sys.stderr)
        return 1

    try:
        from cadforge.viewer.pyvista_viewer import show_stl
        show_stl(path)
        return 0
    except ImportError:
        print("pyvista not installed. Install with: pip install pyvista", file=sys.stderr)
        return 1


def cmd_resume(args: argparse.Namespace) -> int:
    """Resume the last session."""
    from cadforge.utils.paths import find_project_root
    from cadforge.core.session import SessionIndex
    from cadforge.chat.repl import run_repl

    project_root = find_project_root()
    if project_root is None:
        print("No CadForge project found.", file=sys.stderr)
        return 1

    index = SessionIndex(project_root)
    latest = index.get_latest()
    if latest is None:
        print("No previous sessions found.", file=sys.stderr)
        return 1

    print(f"Resuming session: {latest.session_id}")
    run_repl(project_root, session_id=latest.session_id)
    return 0


ALLOWED_CONFIG_KEYS = {"provider", "model", "base_url", "max_tokens", "temperature", "printer"}


def cmd_config(args: argparse.Namespace) -> int:
    """View and update project settings."""
    from cadforge.utils.paths import find_project_root, get_project_settings_path
    from cadforge.config import (
        CadForgeSettings,
        load_json_file,
        load_settings,
        validate_settings,
    )

    project_root = find_project_root()
    if project_root is None:
        print("No CadForge project found.", file=sys.stderr)
        return 1

    action = args.action

    if action == "show":
        settings = load_settings(project_root)
        print(json.dumps(settings.to_dict(), indent=2))
        return 0

    if action == "get":
        if not args.key:
            print("Usage: cadforge config get <key>", file=sys.stderr)
            return 1
        if args.key not in ALLOWED_CONFIG_KEYS:
            print(
                f"Unknown key: {args.key}. "
                f"Allowed keys: {', '.join(sorted(ALLOWED_CONFIG_KEYS))}",
                file=sys.stderr,
            )
            return 1
        settings = load_settings(project_root)
        value = getattr(settings, args.key)
        print(value if value is not None else "")
        return 0

    if action == "set":
        if not args.key or args.value is None:
            print("Usage: cadforge config set <key> <value>", file=sys.stderr)
            return 1
        if args.key not in ALLOWED_CONFIG_KEYS:
            print(
                f"Unknown key: {args.key}. "
                f"Allowed keys: {', '.join(sorted(ALLOWED_CONFIG_KEYS))}",
                file=sys.stderr,
            )
            return 1

        settings_path = get_project_settings_path(project_root)
        data = load_json_file(settings_path)

        # Parse typed values
        value: str | int | float | None = args.value
        if args.key == "max_tokens":
            try:
                value = int(args.value)
            except ValueError:
                print("max_tokens must be an integer", file=sys.stderr)
                return 1
        elif args.key == "temperature":
            try:
                value = float(args.value)
            except ValueError:
                print("temperature must be a number", file=sys.stderr)
                return 1

        data[args.key] = value

        # Validate by building a settings object from merged data
        test_settings = load_settings(project_root)
        setattr(test_settings, args.key, value)
        errors = validate_settings(test_settings)
        if errors:
            for err in errors:
                print(f"Validation error: {err}", file=sys.stderr)
            return 1

        settings_path.parent.mkdir(parents=True, exist_ok=True)
        settings_path.write_text(
            json.dumps(data, indent=2) + "\n", encoding="utf-8"
        )
        print(f"{args.key} = {value}")
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())
