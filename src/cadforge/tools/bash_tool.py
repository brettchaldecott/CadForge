"""Bash tool handler — execute shell commands."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any


def handle_bash(
    tool_input: dict[str, Any],
    project_root: Path,
) -> dict[str, Any]:
    """Execute a shell command."""
    command = tool_input["command"]
    timeout = tool_input.get("timeout", 120)

    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(project_root),
        )
        return {
            "success": result.returncode == 0,
            "exit_code": result.returncode,
            "stdout": result.stdout[:30000],  # Truncate long output
            "stderr": result.stderr[:5000],
        }
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "exit_code": -1,
            "error": f"Command timed out after {timeout}s",
            "stdout": "",
            "stderr": "",
        }
    except Exception as e:
        return {
            "success": False,
            "exit_code": -1,
            "error": str(e),
            "stdout": "",
            "stderr": "",
        }
