"""Project config tool handler — get printer profile."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


def handle_get_printer(
    tool_input: dict[str, Any],
    project_root: Path,
    printer_name: str | None = None,
) -> dict[str, Any]:
    """Get the active printer profile and constraints."""
    if not printer_name:
        return {
            "success": True,
            "printer": None,
            "message": "No printer configured. Set 'printer' in CADFORGE.md or settings.json",
        }

    printer_file = project_root / "vault" / "printers" / f"{printer_name}.md"
    if not printer_file.exists():
        return {
            "success": False,
            "error": f"Printer profile not found: {printer_file}",
        }

    try:
        content = printer_file.read_text(encoding="utf-8")
        frontmatter = _extract_frontmatter(content)
        return {"success": True, "printer": printer_name, "profile": frontmatter}
    except Exception as e:
        return {"success": False, "error": str(e)}


def _extract_frontmatter(content: str) -> dict[str, Any]:
    """Extract YAML frontmatter from a markdown file."""
    if not content.startswith("---"):
        return {}
    parts = content.split("---", 2)
    if len(parts) < 3:
        return {}
    try:
        return yaml.safe_load(parts[1]) or {}
    except yaml.YAMLError:
        return {}
