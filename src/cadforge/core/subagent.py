"""Subagent spawner for CadForge.

Spawns specialized agents with restricted tool sets for
parallel or focused work.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from cadforge.config import CadForgeSettings


@dataclass
class SubagentConfig:
    """Configuration for a subagent."""
    name: str
    agent_type: str  # "explore", "plan", "cad", "custom"
    model: str = "claude-sonnet-4-5-20250929"
    tools: list[str] = field(default_factory=list)
    system_prompt: str = ""
    max_iterations: int = 10

    @classmethod
    def explore(cls) -> SubagentConfig:
        return cls(
            name="explore",
            agent_type="explore",
            model="claude-haiku-4-5-20251001",
            tools=["ReadFile", "ListFiles", "SearchVault", "Bash"],
            system_prompt=(
                "You are an exploration agent for CadForge. "
                "Search, read, and summarize information. "
                "Provide concise, well-structured summaries of your findings. "
                "Do NOT modify any files."
            ),
        )

    @classmethod
    def plan(cls) -> SubagentConfig:
        return cls(
            name="plan",
            agent_type="plan",
            tools=["ReadFile", "ListFiles", "SearchVault"],
            system_prompt=(
                "You are a planning agent for CadForge. "
                "Analyze requirements, read existing code and vault documents, "
                "and design implementation approaches. "
                "Return a clear, actionable plan with specific steps. "
                "Do NOT modify any files."
            ),
        )

    @classmethod
    def cad(cls) -> SubagentConfig:
        return cls(
            name="cad",
            agent_type="cad",
            tools=["ExecuteCadQuery", "AnalyzeMesh", "ExportModel", "ReadFile", "SearchVault"],
            system_prompt=(
                "You are a CAD generation agent for CadForge. "
                "Create 3D models using CadQuery. Assign the final workpiece to `result`. "
                "Use `cq` as the CadQuery namespace and `np` for numpy. "
                "You can read files and search the vault for reference material."
            ),
            max_iterations=20,
        )


@dataclass
class SubagentResult:
    """Result from a subagent execution."""
    agent_name: str
    success: bool
    output: str
    error: str | None = None


def get_available_agent_types() -> list[str]:
    """Get list of available subagent types."""
    return ["explore", "plan", "cad", "custom"]


def create_subagent_config(
    agent_type: str,
    custom_config: dict[str, Any] | None = None,
) -> SubagentConfig:
    """Create a subagent configuration by type."""
    if agent_type == "explore":
        return SubagentConfig.explore()
    elif agent_type == "plan":
        return SubagentConfig.plan()
    elif agent_type == "cad":
        return SubagentConfig.cad()
    elif agent_type == "custom" and custom_config:
        return SubagentConfig(
            name=custom_config.get("name", "custom"),
            agent_type="custom",
            model=custom_config.get("model", "claude-sonnet-4-5-20250929"),
            tools=custom_config.get("tools", []),
            system_prompt=custom_config.get("system_prompt", ""),
            max_iterations=custom_config.get("max_iterations", 10),
        )
    else:
        raise ValueError(f"Unknown agent type: {agent_type}")
