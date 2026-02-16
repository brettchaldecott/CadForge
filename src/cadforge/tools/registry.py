"""Tool registry for CadForge.

Defines all available tools with their JSON schemas for the Anthropic API.
"""

from __future__ import annotations

from typing import Any


def get_tool_definitions() -> list[dict[str, Any]]:
    """Return all tool definitions in Anthropic API tool format."""
    return [
        {
            "name": "ExecuteCadQuery",
            "description": (
                "Execute CadQuery Python code to create 3D models. "
                "The code runs in a sandboxed environment with cadquery (cq), math, and numpy (np) available. "
                "Assign the final workpiece to 'result' to export it. "
                "Returns mesh statistics and the output file path."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "code": {
                        "type": "string",
                        "description": "CadQuery Python code to execute",
                    },
                    "output_name": {
                        "type": "string",
                        "description": "Name for the output file (without extension)",
                        "default": "model",
                    },
                    "format": {
                        "type": "string",
                        "enum": ["stl", "step"],
                        "description": "Export format",
                        "default": "stl",
                    },
                },
                "required": ["code"],
            },
        },
        {
            "name": "ReadFile",
            "description": "Read the contents of a file.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path to the file to read",
                    },
                },
                "required": ["path"],
            },
        },
        {
            "name": "WriteFile",
            "description": "Write content to a file, creating directories as needed.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path to write the file",
                    },
                    "content": {
                        "type": "string",
                        "description": "Content to write",
                    },
                },
                "required": ["path", "content"],
            },
        },
        {
            "name": "ListFiles",
            "description": "List files and directories matching a glob pattern.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "pattern": {
                        "type": "string",
                        "description": "Glob pattern (e.g., '**/*.py', 'vault/*.md')",
                        "default": "*",
                    },
                    "path": {
                        "type": "string",
                        "description": "Base directory to search from",
                        "default": ".",
                    },
                },
                "required": [],
            },
        },
        {
            "name": "SearchVault",
            "description": (
                "Search the knowledge vault using hybrid vector + full-text search. "
                "Returns relevant sections from materials, design rules, CadQuery patterns, "
                "and printer profiles."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Natural language search query",
                    },
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional tags to filter results (e.g., ['PLA', 'material'])",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of results",
                        "default": 5,
                    },
                },
                "required": ["query"],
            },
        },
        {
            "name": "AnalyzeMesh",
            "description": (
                "Analyze a 3D mesh file (STL/3MF) for watertightness, volume, "
                "surface area, bounding box, and potential issues."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path to the mesh file",
                    },
                },
                "required": ["path"],
            },
        },
        {
            "name": "ShowPreview",
            "description": "Open an interactive 3D viewer for an STL file.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path to the STL file to preview",
                    },
                },
                "required": ["path"],
            },
        },
        {
            "name": "ExportModel",
            "description": "Export a previously generated model to STEP or 3MF format.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "source": {
                        "type": "string",
                        "description": "Path to the source STL or model file",
                    },
                    "format": {
                        "type": "string",
                        "enum": ["step", "3mf"],
                        "description": "Target export format",
                    },
                    "name": {
                        "type": "string",
                        "description": "Output filename (without extension)",
                    },
                },
                "required": ["source", "format"],
            },
        },
        {
            "name": "Bash",
            "description": (
                "Execute a shell command. Use for git operations, file system tasks, "
                "and other terminal operations."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "The shell command to execute",
                    },
                    "timeout": {
                        "type": "integer",
                        "description": "Timeout in seconds",
                        "default": 120,
                    },
                },
                "required": ["command"],
            },
        },
        {
            "name": "GetPrinter",
            "description": "Get the active printer profile with build constraints.",
            "input_schema": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
        {
            "name": "SearchWeb",
            "description": "Search the web for engineering references and documentation.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query",
                    },
                },
                "required": ["query"],
            },
        },
    ]


def get_tool_names() -> list[str]:
    """Get list of all tool names."""
    return [t["name"] for t in get_tool_definitions()]


def get_tool_definition(name: str) -> dict[str, Any] | None:
    """Get a specific tool definition by name."""
    for tool in get_tool_definitions():
        if tool["name"] == name:
            return tool
    return None
