"""Task tool handler — delegate focused tasks to sub-agents."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from cadforge.core.subagent import create_subagent_config, get_available_agent_types
from cadforge.core.subagent_executor import run_subagent, run_subagent_async

if TYPE_CHECKING:
    from cadforge.core.agent import Agent


def handle_task(tool_input: dict[str, Any], agent: Agent) -> dict[str, Any]:
    """Spawn a sub-agent to handle a focused task.

    Args:
        tool_input: Must contain 'agent_type' and 'prompt', optionally 'context'.
        agent: The parent Agent instance (provides provider, settings, etc.)

    Returns:
        Dict with success, output, agent_name, and error fields.
    """
    agent_type = tool_input.get("agent_type", "")
    prompt = tool_input.get("prompt", "")
    context = tool_input.get("context", "")

    if not prompt:
        return {
            "success": False,
            "output": "",
            "agent_name": "",
            "error": "prompt is required",
        }

    valid_types = get_available_agent_types()
    if agent_type not in valid_types or agent_type == "custom":
        return {
            "success": False,
            "output": "",
            "agent_name": "",
            "error": f"Invalid agent_type '{agent_type}'. Must be one of: explore, plan, cad",
        }

    config = create_subagent_config(agent_type)
    result = run_subagent(
        config=config,
        task_prompt=prompt,
        context=context,
        provider=agent._provider,
        settings=agent.settings,
        project_root=agent.project_root,
        permissions=agent.settings.permissions,
        ask_callback=agent.ask_callback,
    )

    return {
        "success": result.success,
        "output": result.output,
        "agent_name": result.agent_name,
        "error": result.error,
    }


async def handle_task_async(tool_input: dict[str, Any], agent: Agent) -> dict[str, Any]:
    """Async version of handle_task — uses async sub-agent executor."""
    agent_type = tool_input.get("agent_type", "")
    prompt = tool_input.get("prompt", "")
    context = tool_input.get("context", "")

    if not prompt:
        return {
            "success": False,
            "output": "",
            "agent_name": "",
            "error": "prompt is required",
        }

    valid_types = get_available_agent_types()
    if agent_type not in valid_types or agent_type == "custom":
        return {
            "success": False,
            "output": "",
            "agent_name": "",
            "error": f"Invalid agent_type '{agent_type}'. Must be one of: explore, plan, cad",
        }

    config = create_subagent_config(agent_type)
    result = await run_subagent_async(
        config=config,
        task_prompt=prompt,
        context=context,
        async_provider=agent._get_async_provider(),
        settings=agent.settings,
        project_root=agent.project_root,
        permissions=agent.settings.permissions,
        ask_callback=agent.ask_callback,
    )

    return {
        "success": result.success,
        "output": result.output,
        "agent_name": result.agent_name,
        "error": result.error,
    }
