"""CadForge CLI — main entry point.

Commands:
  chat      Start interactive chat session
  init      Initialize a new CadForge project
  index     Index the knowledge vault
  view      Preview an STL file
  resume    Resume the last session
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


if __name__ == "__main__":
    sys.exit(main())
