"""CadQuery tool handler — execute CadQuery code and export results."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from cadforge.cad.sandbox import execute_cadquery
from cadforge.utils.paths import get_stl_output_dir, get_step_output_dir


def handle_execute_cadquery(
    tool_input: dict[str, Any],
    project_root: Path,
) -> dict[str, Any]:
    """Execute CadQuery code and optionally export the result."""
    code = tool_input["code"]
    output_name = tool_input.get("output_name", "model")
    fmt = tool_input.get("format", "stl")

    if fmt == "step":
        output_dir = get_step_output_dir(project_root)
        output_path = output_dir / f"{output_name}.step"
    else:
        output_dir = get_stl_output_dir(project_root)
        output_path = output_dir / f"{output_name}.stl"

    result = execute_cadquery(code, output_path=output_path)

    if not result.success:
        return {
            "success": False,
            "error": result.error,
            "stdout": result.stdout,
            "stderr": result.stderr,
        }

    response: dict[str, Any] = {
        "success": True,
        "stdout": result.stdout,
    }

    if result.has_workpiece:
        response["output_path"] = str(output_path)
        response["message"] = f"Model exported to {output_path}"
    else:
        response["message"] = "Code executed successfully (no result variable set)"

    return response
