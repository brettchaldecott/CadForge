"""Task-based API for async task management.

Provides REST endpoints for creating, polling, and streaming tasks.
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field

from cadforge_engine.models.tasks import (
    TaskModel,
    TaskStatus,
    TaskStore,
    TaskType,
    task_store,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tasks")


class CreateTaskRequest(BaseModel):
    """Request to create a new task."""
    type: TaskType
    prompt: str = Field(default="", description="Task prompt")
    project_root: str = Field(default=".", description="Project root directory")
    config: dict[str, Any] = Field(default_factory=dict, description="Task-specific configuration")


class CreateTaskResponse(BaseModel):
    """Response from task creation."""
    task_id: str
    status: str


class TaskStatusResponse(BaseModel):
    """Task status response."""
    id: str
    type: str
    status: str
    prompt: str
    artifacts: dict[str, str]
    result: dict[str, Any] | None
    error: str | None
    created_at: str
    started_at: str | None
    completed_at: str | None


@router.post("", response_model=CreateTaskResponse)
async def create_task(req: CreateTaskRequest) -> CreateTaskResponse:
    """Create a new async task."""
    task = task_store.create(req.type, req.prompt)

    # Launch task execution in background
    asyncio.create_task(_execute_task(task.id, req))

    return CreateTaskResponse(task_id=task.id, status=task.status.value)


@router.get("/{task_id}", response_model=TaskStatusResponse)
async def get_task(task_id: str) -> TaskStatusResponse:
    """Get task status and results."""
    task = task_store.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")

    return TaskStatusResponse(
        id=task.id,
        type=task.type.value,
        status=task.status.value,
        prompt=task.prompt,
        artifacts=task.artifacts,
        result=task.result,
        error=task.error,
        created_at=task.created_at,
        started_at=task.started_at,
        completed_at=task.completed_at,
    )


@router.get("/{task_id}/stream")
async def stream_task(task_id: str) -> StreamingResponse:
    """Stream task events via SSE."""
    task = task_store.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")

    async def event_generator():
        last_index = 0
        while True:
            task = task_store.get(task_id)
            if not task:
                break

            # Yield any new events
            while last_index < len(task.events):
                event = task.events[last_index]
                event_type = event.get("event", "status")
                data = event.get("data", {})
                yield f"event: {event_type}\ndata: {json.dumps(data)}\n\n"
                last_index += 1

            # Check if task is done
            if task.status in (TaskStatus.COMPLETED, TaskStatus.FAILED):
                yield f"event: done\ndata: {json.dumps({'status': task.status.value})}\n\n"
                break

            await asyncio.sleep(0.1)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )


@router.get("/{task_id}/artifacts/{name}")
async def get_artifact(task_id: str, name: str) -> FileResponse:
    """Download a task artifact."""
    task = task_store.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")

    artifact_path = task.artifacts.get(name)
    if not artifact_path:
        raise HTTPException(status_code=404, detail=f"Artifact '{name}' not found")

    path = Path(artifact_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Artifact file not found: {path}")

    return FileResponse(path, filename=path.name)


async def _execute_task(task_id: str, req: CreateTaskRequest) -> None:
    """Execute a task in the background."""
    task_store.update_status(task_id, TaskStatus.RUNNING)

    try:
        if req.type == TaskType.EXECUTE_CAD:
            await _run_execute_cad(task_id, req)
        elif req.type == TaskType.ANALYZE_MESH:
            await _run_analyze_mesh(task_id, req)
        elif req.type == TaskType.DESIGN_PIPELINE:
            await _run_design_pipeline(task_id, req)
        elif req.type == TaskType.CAD_SUBAGENT:
            await _run_cad_subagent(task_id, req)
        else:
            task_store.set_error(task_id, f"Unknown task type: {req.type}")
            task_store.update_status(task_id, TaskStatus.FAILED)
            return

        task_store.update_status(task_id, TaskStatus.COMPLETED)

    except Exception as e:
        logger.exception("Task %s failed", task_id)
        task_store.set_error(task_id, str(e))
        task_store.update_status(task_id, TaskStatus.FAILED)


async def _run_execute_cad(task_id: str, req: CreateTaskRequest) -> None:
    """Execute CAD code."""
    from cadforge_engine.domain.sandbox import execute_cadquery

    code = req.config.get("code", req.prompt)
    output_name = req.config.get("output_name", "model")
    fmt = req.config.get("format", "stl")

    pr = Path(req.project_root)
    output_dir = pr / "output" / fmt
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{output_name}.{fmt}"

    result = execute_cadquery(code, output_path=output_path)

    if result.success and result.has_workpiece:
        task_store.add_artifact(task_id, f"model.{fmt}", str(output_path))

    task_store.set_result(task_id, {
        "success": result.success,
        "stdout": result.stdout,
        "error": result.error,
        "output_path": str(output_path) if result.has_workpiece else None,
    })

    if not result.success:
        task_store.set_error(task_id, result.error or "Execution failed")
        task_store.update_status(task_id, TaskStatus.FAILED)


async def _run_analyze_mesh(task_id: str, req: CreateTaskRequest) -> None:
    """Analyze a mesh file."""
    from cadforge_engine.domain.analyzer import analyze_mesh

    path = Path(req.config.get("path", req.prompt))
    if not path.is_absolute():
        path = Path(req.project_root) / path

    analysis = analyze_mesh(path)
    task_store.set_result(task_id, analysis.to_dict())


async def _run_design_pipeline(task_id: str, req: CreateTaskRequest) -> None:
    """Run the design pipeline."""
    from cadforge_engine.agent.llm import create_subagent_client
    from cadforge_engine.agent.pipeline import run_design_pipeline

    provider_config = req.config.get("provider_config")
    if not provider_config:
        task_store.set_error(task_id, "No provider_config in task config")
        task_store.update_status(task_id, TaskStatus.FAILED)
        return

    llm_client = create_subagent_client(
        provider_config,
        model=req.config.get("model", "claude-sonnet-4-5-20250929"),
        max_tokens=req.config.get("max_tokens", 8192),
    )

    async for event in run_design_pipeline(
        llm_client=llm_client,
        prompt=req.prompt,
        project_root=req.project_root,
        max_rounds=req.config.get("max_rounds", 3),
    ):
        task_store.add_event(task_id, event)

        # Capture output path as artifact
        if event.get("event") == "completion":
            output_path = event.get("data", {}).get("output_path")
            if output_path:
                task_store.add_artifact(task_id, "model.stl", output_path)
            task_store.set_result(task_id, event.get("data", {}))


async def _run_cad_subagent(task_id: str, req: CreateTaskRequest) -> None:
    """Run the CAD subagent."""
    from cadforge_engine.agent.llm import create_subagent_client
    from cadforge_engine.agent.cad_agent import run_cad_subagent

    provider_config = req.config.get("provider_config")
    if not provider_config:
        task_store.set_error(task_id, "No provider_config in task config")
        task_store.update_status(task_id, TaskStatus.FAILED)
        return

    llm_client = create_subagent_client(
        provider_config,
        model=req.config.get("model", "claude-sonnet-4-5-20250929"),
        max_tokens=req.config.get("max_tokens", 8192),
    )

    async for event in run_cad_subagent(
        llm_client=llm_client,
        prompt=req.prompt,
        context=req.config.get("context", ""),
        project_root=req.project_root,
    ):
        task_store.add_event(task_id, event)

        if event.get("event") == "completion":
            task_store.set_result(task_id, event.get("data", {}))
