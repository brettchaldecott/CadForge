"""CAD subagent — runs an agentic loop with CadQuery tools.

Iterates on CadQuery code, analyzing mesh output and refining models
until the user's intent is satisfied. Streams SSE events back to the
Node CLI via an async generator.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, AsyncGenerator

from cadforge_engine.agent.llm import SubagentLLMClient

logger = logging.getLogger(__name__)

MAX_ITERATIONS = 20

CAD_SYSTEM_PROMPT = """\
You are the CadForge CAD subagent. You generate and refine 3D models using CadQuery or build123d.

Library choice:
- CadQuery (`cq`): Mature, fluent workplane API. Best for parametric parts with features on faces.
- build123d (`bd`): Modern Python-native API with context managers. Best for complex topology, assemblies, and builder patterns.
- Both are available in the sandbox. Choose whichever fits the task best.

Rules:
- Assign the final workpiece to `result` in your code
- CadQuery: use `cq` namespace, result should be a `cq.Workplane`
- build123d: use `bd` namespace or top-level names (Box, Cylinder, etc.), result should be a `Part`, `Compound`, or `Shape`
- Use `np` for numpy
- After generating code, analyze the mesh to verify correctness
- If the mesh has issues, refine the code and try again
- Keep code clean and well-commented

Available tools: ExecuteCadQuery, AnalyzeMesh, RenderModel, ExportModel, ReadFile, SearchVault
"""

CAD_TOOLS: list[dict[str, Any]] = [
    {
        "name": "ExecuteCadQuery",
        "description": "Execute CadQuery or build123d code to create or modify 3D models. Assign final workpiece to `result`.",
        "input_schema": {
            "type": "object",
            "properties": {
                "code": {"type": "string", "description": "CadQuery Python code"},
                "output_name": {"type": "string", "description": "Output filename (without extension)"},
                "format": {"type": "string", "enum": ["stl", "step"], "description": "Export format"},
            },
            "required": ["code"],
        },
    },
    {
        "name": "AnalyzeMesh",
        "description": "Analyze a mesh file for geometry metrics and manufacturing issues.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Path to mesh file"},
            },
            "required": ["path"],
        },
    },
    {
        "name": "ExportModel",
        "description": "Export a model to a different format (stl, step, 3mf).",
        "input_schema": {
            "type": "object",
            "properties": {
                "source": {"type": "string", "description": "Source model path"},
                "format": {"type": "string", "enum": ["stl", "step", "3mf"], "description": "Target format"},
                "name": {"type": "string", "description": "Output filename"},
            },
            "required": ["source"],
        },
    },
    {
        "name": "RenderModel",
        "description": "Render a 3D model (STL file) to PNG images from multiple camera angles for visual inspection.",
        "input_schema": {
            "type": "object",
            "properties": {
                "stl_path": {"type": "string", "description": "Path to the STL file to render"},
                "output_dir": {"type": "string", "description": "Output directory for PNGs"},
                "include_base64": {"type": "boolean", "description": "Include base64 image data"},
            },
            "required": ["stl_path"],
        },
    },
    {
        "name": "ReadFile",
        "description": "Read the contents of a file.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File path to read"},
            },
            "required": ["path"],
        },
    },
    {
        "name": "SearchVault",
        "description": "Search the knowledge vault for relevant information.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"},
                "tags": {"type": "array", "items": {"type": "string"}, "description": "Filter by tags"},
                "limit": {"type": "number", "description": "Max results"},
            },
            "required": ["query"],
        },
    },
]


def _handle_tool(
    tool_name: str,
    tool_input: dict[str, Any],
    project_root: Path,
) -> dict[str, Any]:
    """Execute a tool call and return the result dict."""
    try:
        if tool_name == "ExecuteCadQuery":
            from cadforge_engine.domain.sandbox import execute_cadquery

            code = tool_input["code"]
            output_name = tool_input.get("output_name", "model")
            fmt = tool_input.get("format", "stl")

            if fmt == "step":
                output_dir = project_root / "output" / "step"
                output_path = output_dir / f"{output_name}.step"
            else:
                output_dir = project_root / "output" / "stl"
                output_path = output_dir / f"{output_name}.stl"
            output_dir.mkdir(parents=True, exist_ok=True)

            result = execute_cadquery(code, output_path=output_path)
            if not result.success:
                return {"success": False, "error": result.error, "stdout": result.stdout, "stderr": result.stderr}

            resp: dict[str, Any] = {"success": True, "stdout": result.stdout}
            if result.has_workpiece:
                resp["output_path"] = str(output_path)
                resp["message"] = f"Model exported to {output_path}"
            else:
                resp["message"] = "Code executed successfully (no result variable set)"
            return resp

        elif tool_name == "AnalyzeMesh":
            from cadforge_engine.domain.analyzer import analyze_mesh

            path = Path(tool_input["path"])
            if not path.is_absolute():
                path = project_root / path
            analysis = analyze_mesh(path)
            return {"success": True, **analysis.to_dict()}

        elif tool_name == "ExportModel":
            from cadforge_engine.domain.exporter import export_stl, export_step, export_3mf

            source = Path(tool_input["source"])
            if not source.is_absolute():
                source = project_root / source
            fmt = tool_input.get("format", "step")
            name = tool_input.get("name", "model")
            output_dir = project_root / "output" / fmt

            if fmt == "stl":
                # Re-export requires loading mesh; for now delegate to sandbox
                return {"success": False, "error": "Use ExecuteCadQuery with format='stl' instead"}
            elif fmt == "step":
                return {"success": False, "error": "Use ExecuteCadQuery with format='step' instead"}
            else:
                return {"success": False, "error": f"Unsupported export format: {fmt}"}

        elif tool_name == "RenderModel":
            from cadforge_engine.domain.renderer import render_stl_to_png

            stl = Path(tool_input["stl_path"])
            if not stl.is_absolute():
                stl = project_root / stl
            out_dir = Path(tool_input["output_dir"]) if tool_input.get("output_dir") else stl.parent
            png_base = out_dir / stl.stem
            paths = render_stl_to_png(stl, png_base)
            return {
                "success": True,
                "images": [str(p) for p in paths],
                "message": f"Rendered {len(paths)} views",
            }

        elif tool_name == "ReadFile":
            path = Path(tool_input["path"])
            if not path.is_absolute():
                path = project_root / path
            if not path.exists():
                return {"success": False, "error": f"File not found: {path}"}
            content = path.read_text(encoding="utf-8")
            return {"success": True, "content": content}

        elif tool_name == "SearchVault":
            from cadforge_engine.vault.search import search_vault

            results = search_vault(
                project_root,
                tool_input["query"],
                tags=tool_input.get("tags"),
                limit=tool_input.get("limit", 5),
            )
            return {"success": True, "results": results}

        else:
            return {"success": False, "error": f"Unknown tool: {tool_name}"}

    except Exception as e:
        logger.exception("Tool %s failed", tool_name)
        return {"success": False, "error": str(e)}


async def run_cad_subagent(
    llm_client: SubagentLLMClient,
    prompt: str,
    context: str,
    project_root: str,
) -> AsyncGenerator[dict[str, Any], None]:
    """Run the CAD subagent agentic loop, yielding SSE event dicts.

    Events yielded:
    - {"event": "status", "data": {"message": "..."}}
    - {"event": "tool_use_start", "data": {"name": "...", "id": "...", "input": {...}}}
    - {"event": "tool_result", "data": {"name": "...", "id": "...", "result": {...}}}
    - {"event": "completion", "data": {"text": "..."}}
    - {"event": "done", "data": {}}
    """
    pr = Path(project_root)

    # Build initial messages
    user_content = prompt
    if context:
        user_content = f"{context}\n\n{prompt}"

    messages: list[dict[str, Any]] = [
        {"role": "user", "content": user_content},
    ]

    yield {"event": "status", "data": {"message": "CAD subagent starting..."}}

    for iteration in range(MAX_ITERATIONS):
        yield {"event": "status", "data": {"message": f"Thinking (iteration {iteration + 1})..."}}

        try:
            response = llm_client.call(
                messages=messages,
                system=CAD_SYSTEM_PROMPT,
                tools=CAD_TOOLS,
            )
        except Exception as e:
            logger.exception("LLM call failed in CAD subagent")
            yield {"event": "completion", "data": {"text": f"LLM error: {e}"}}
            yield {"event": "done", "data": {}}
            return

        content = response["content"]
        stop_reason = response["stop_reason"]

        # Separate text and tool uses
        text_parts: list[str] = []
        tool_uses: list[dict[str, Any]] = []

        for block in content:
            if block["type"] == "text":
                text_parts.append(block["text"])
            elif block["type"] == "tool_use":
                tool_uses.append(block)

        # No tool use — done
        if not tool_uses:
            final_text = "\n".join(text_parts)
            yield {"event": "completion", "data": {"text": final_text}}
            yield {"event": "done", "data": {}}
            return

        # Record assistant message
        messages.append({"role": "assistant", "content": content})

        # Execute tools
        tool_results: list[dict[str, Any]] = []
        for tool_use in tool_uses:
            name = tool_use["name"]
            tool_id = tool_use["id"]
            tool_input = tool_use["input"]

            yield {"event": "tool_use_start", "data": {"name": name, "id": tool_id, "input": tool_input}}

            result = _handle_tool(name, tool_input, pr)

            yield {"event": "tool_result", "data": {"name": name, "id": tool_id, "result": result}}

            tool_results.append({
                "type": "tool_result",
                "tool_use_id": tool_id,
                "content": json.dumps(result),
            })

        # Add tool results as user message
        messages.append({"role": "user", "content": tool_results})

    # Max iterations reached
    yield {"event": "completion", "data": {"text": "Maximum iterations reached."}}
    yield {"event": "done", "data": {}}
