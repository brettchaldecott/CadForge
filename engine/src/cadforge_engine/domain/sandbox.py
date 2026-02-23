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

    # build123d
    try:
        import build123d as bd
        namespace["bd"] = bd
        namespace["build123d"] = bd
        # Expose common builder classes at top level for tutorial-style usage
        for _name in (
            # 3D primitives
            "Box", "Cylinder", "Sphere", "Cone", "Torus", "Wedge",
            # Builders
            "Part", "BuildPart", "BuildSketch", "BuildLine",
            # 2D sketch shapes
            "Sketch", "Line", "Circle", "Rectangle", "Polygon",
            "RegularPolygon", "Text",
            # Operations (lowercase in build123d)
            "extrude", "revolve", "loft", "sweep", "section",
            "fillet", "chamfer", "offset",
            # Shell is capitalized
            "Shell",
            # Positioning
            "Location", "Locations", "Rotation",
            "GridLocations", "PolarLocations",
            # Geometry
            "Axis", "Plane", "Vector",
            # Enums
            "Mode", "Align", "Kind",
            # Helpers
            "make_face", "export_step", "export_stl",
        ):
            if hasattr(bd, _name):
                namespace[_name] = getattr(bd, _name)
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
        _NAMESPACE_NAMES = {
            "cq", "cadquery", "bd", "build123d", "math", "np", "numpy",
            "__builtins__",
            # build123d top-level exports
            "Box", "Cylinder", "Sphere", "Cone", "Torus", "Wedge",
            "Part", "BuildPart", "BuildSketch", "BuildLine",
            "Sketch", "Line", "Circle", "Rectangle", "Polygon",
            "RegularPolygon", "Text",
            "extrude", "revolve", "loft", "sweep", "section",
            "fillet", "chamfer", "offset",
            "Shell",
            "Location", "Locations", "Rotation",
            "GridLocations", "PolarLocations",
            "Axis", "Plane", "Vector",
            "Mode", "Align", "Kind",
            "make_face", "export_step", "export_stl",
        }
        user_vars = {
            k: v for k, v in namespace.items()
            if not k.startswith("_") and k not in _NAMESPACE_NAMES
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
    """Export a CadQuery or build123d result to file based on extension."""
    path.parent.mkdir(parents=True, exist_ok=True)
    suffix = path.suffix.lower()

    # Try CadQuery first (existing behavior)
    try:
        import cadquery as cq
        if isinstance(result, cq.Workplane):
            if suffix == ".stl":
                cq.exporters.export(result, str(path), exportType="STL")
            elif suffix == ".step":
                cq.exporters.export(result, str(path), exportType="STEP")
            else:
                cq.exporters.export(result, str(path))
            return
    except ImportError:
        pass

    # Try build123d
    try:
        import build123d as bd
        # build123d Part, Compound, and Shape types
        if isinstance(result, (bd.Part, bd.Compound, bd.Shape)):
            if suffix == ".stl":
                bd.export_stl(result, str(path))
            elif suffix == ".step":
                bd.export_step(result, str(path))
            else:
                bd.export_step(result, str(path))
            return
    except ImportError:
        pass

    raise TypeError(
        f"Cannot export {type(result).__name__}; "
        f"expected cq.Workplane or build123d Part/Compound/Shape"
    )
