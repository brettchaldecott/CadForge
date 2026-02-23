"""Task state model for async task management."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class TaskStatus(str, Enum):
    """Task lifecycle status."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class TaskType(str, Enum):
    """Types of tasks the service can execute."""
    EXECUTE_CAD = "execute_cad"
    ANALYZE_MESH = "analyze_mesh"
    DESIGN_PIPELINE = "design_pipeline"
    CAD_SUBAGENT = "cad_subagent"


class TaskModel(BaseModel):
    """A managed async task."""
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    type: TaskType
    status: TaskStatus = TaskStatus.PENDING
    prompt: str = ""
    artifacts: dict[str, str] = Field(default_factory=dict)
    events: list[dict[str, Any]] = Field(default_factory=list)
    result: dict[str, Any] | None = None
    error: str | None = None
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    started_at: str | None = None
    completed_at: str | None = None


class TaskStore:
    """In-memory task store."""

    def __init__(self) -> None:
        self._tasks: dict[str, TaskModel] = {}

    def create(self, task_type: TaskType, prompt: str = "") -> TaskModel:
        task = TaskModel(type=task_type, prompt=prompt)
        self._tasks[task.id] = task
        return task

    def get(self, task_id: str) -> TaskModel | None:
        return self._tasks.get(task_id)

    def update_status(self, task_id: str, status: TaskStatus) -> None:
        task = self._tasks.get(task_id)
        if task:
            task.status = status
            now = datetime.now(timezone.utc).isoformat()
            if status == TaskStatus.RUNNING:
                task.started_at = now
            elif status in (TaskStatus.COMPLETED, TaskStatus.FAILED):
                task.completed_at = now

    def add_event(self, task_id: str, event: dict[str, Any]) -> None:
        task = self._tasks.get(task_id)
        if task:
            task.events.append(event)

    def add_artifact(self, task_id: str, name: str, path: str) -> None:
        task = self._tasks.get(task_id)
        if task:
            task.artifacts[name] = path

    def set_result(self, task_id: str, result: dict[str, Any]) -> None:
        task = self._tasks.get(task_id)
        if task:
            task.result = result

    def set_error(self, task_id: str, error: str) -> None:
        task = self._tasks.get(task_id)
        if task:
            task.error = error

    def list_all(self) -> list[TaskModel]:
        return list(self._tasks.values())


# Global singleton store
task_store = TaskStore()
