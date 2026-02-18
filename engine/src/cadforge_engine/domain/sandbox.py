"""Sandboxed CadQuery execution environment.

Provides a restricted exec() namespace with CadQuery, math, and numpy available.
Prevents access to dangerous builtins like open, exec, eval, __import__.
"""

from __future__ import annotations

import io
import sys
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


# Safe builtins whitelist
SAFE_BUILTINS = {
    "abs", "all", "any", "bool", "dict", "divmod", "enumerate",
    "filter", "float", "frozenset", "getattr", "hasattr", "hash",
    "int", "isinstance", "issubclass", "iter", "len", "list",
    "map", "max", "min", "next", "pow", "print", "range",
    "repr", "reversed", "round", "set", "slice", "sorted",
    "str", "sum", "tuple", "type", "zip",
}


@dataclass
class SandboxResult:
    """Result from sandbox execution."""
    success: bool
    result: Any = None
    stdout: str = ""
    stderr: str = ""
    error: str | None = None
    variables: dict[str, Any] = field(default_factory=dict)

    @property
    def has_workpiece(self) -> bool:
        """Check if a CadQuery workpiece was produced."""
        return "result" in self.variables or "r" in self.variables


def _make_safe_builtins() -> dict[str, Any]:
    """Create a restricted builtins dict."""
    import builtins
    safe = {}
    for name in SAFE_BUILTINS:
        if hasattr(builtins, name):
            safe[name] = getattr(builtins, name)
    return safe


def build_namespace() -> dict[str, Any]:
    """Build the sandboxed execution namespace.

    Includes: cadquery (cq), math, numpy (np)
    Excludes: file I/O, os, subprocess, __import__
    """
    namespace: dict[str, Any] = {}
    namespace["__builtins__"] = _make_safe_builtins()

    # CadQuery
    try:
        import cadquery as cq
        namespace["cq"] = cq
        namespace["cadquery"] = cq
    except ImportError:
        pass

    # Math
    import math
    namespace["math"] = math

    # NumPy
    try:
        import numpy as np
        namespace["np"] = np
        namespace["numpy"] = np
    except ImportError:
        pass

    return namespace


def execute_cadquery(
    code: str,
    output_path: Path | None = None,
    extra_namespace: dict[str, Any] | None = None,
) -> SandboxResult:
    """Execute CadQuery code in a sandboxed environment.

    Args:
        code: Python/CadQuery code to execute
        output_path: Optional path to export result as STL
        extra_namespace: Additional variables to inject

    Returns:
        SandboxResult with success status, output, and any CadQuery result
    """
    namespace = build_namespace()
    if extra_namespace:
        namespace.update(extra_namespace)

    # Capture stdout/stderr
    old_stdout, old_stderr = sys.stdout, sys.stderr
    captured_out = io.StringIO()
    captured_err = io.StringIO()

    try:
        sys.stdout = captured_out
        sys.stderr = captured_err

        exec(code, namespace)  # noqa: S102

        # Look for result variable
        result_var = namespace.get("result") or namespace.get("r")

        # Auto-export if we have a result and output path
        if result_var is not None and output_path is not None:
            try:
                _export_result(result_var, output_path)
            except Exception as e:
                return SandboxResult(
                    success=False,
                    error=f"Export failed: {e}",
                    stdout=captured_out.getvalue(),
                    stderr=captured_err.getvalue(),
                )

        # Collect user-defined variables (exclude internals)
        user_vars = {
            k: v for k, v in namespace.items()
            if not k.startswith("_") and k not in (
                "cq", "cadquery", "math", "np", "numpy", "__builtins__"
            )
        }

        return SandboxResult(
            success=True,
            result=result_var,
            stdout=captured_out.getvalue(),
            stderr=captured_err.getvalue(),
            variables=user_vars,
        )

    except Exception as e:
        tb = traceback.format_exc()
        return SandboxResult(
            success=False,
            error=str(e),
            stdout=captured_out.getvalue(),
            stderr=captured_err.getvalue() + "\n" + tb,
        )
    finally:
        sys.stdout = old_stdout
        sys.stderr = old_stderr


def _export_result(result: Any, path: Path) -> None:
    """Export a CadQuery result to file based on extension."""
    try:
        import cadquery as cq
    except ImportError:
        raise RuntimeError("CadQuery not available for export")

    path.parent.mkdir(parents=True, exist_ok=True)
    suffix = path.suffix.lower()

    if isinstance(result, cq.Workplane):
        if suffix == ".stl":
            cq.exporters.export(result, str(path), exportType="STL")
        elif suffix == ".step":
            cq.exporters.export(result, str(path), exportType="STEP")
        else:
            cq.exporters.export(result, str(path))
    else:
        raise TypeError(f"Cannot export {type(result).__name__}, expected cq.Workplane")
