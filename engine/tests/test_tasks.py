"""Tests for the task-based API."""

from __future__ import annotations

import pytest

from cadforge_engine.models.tasks import TaskModel, TaskStatus, TaskStore, TaskType


class TestTaskStore:
    """Test the in-memory task store."""

    def test_create_task(self) -> None:
        store = TaskStore()
        task = store.create(TaskType.EXECUTE_CAD, "make a box")
        assert task.id
        assert task.type == TaskType.EXECUTE_CAD
        assert task.status == TaskStatus.PENDING
        assert task.prompt == "make a box"

    def test_get_task(self) -> None:
        store = TaskStore()
        task = store.create(TaskType.ANALYZE_MESH)
        fetched = store.get(task.id)
        assert fetched is not None
        assert fetched.id == task.id

    def test_get_missing_task(self) -> None:
        store = TaskStore()
        assert store.get("nonexistent") is None

    def test_update_status_running(self) -> None:
        store = TaskStore()
        task = store.create(TaskType.EXECUTE_CAD)
        store.update_status(task.id, TaskStatus.RUNNING)
        assert task.status == TaskStatus.RUNNING
        assert task.started_at is not None

    def test_update_status_completed(self) -> None:
        store = TaskStore()
        task = store.create(TaskType.EXECUTE_CAD)
        store.update_status(task.id, TaskStatus.RUNNING)
        store.update_status(task.id, TaskStatus.COMPLETED)
        assert task.status == TaskStatus.COMPLETED
        assert task.completed_at is not None

    def test_update_status_failed(self) -> None:
        store = TaskStore()
        task = store.create(TaskType.EXECUTE_CAD)
        store.update_status(task.id, TaskStatus.FAILED)
        assert task.status == TaskStatus.FAILED
        assert task.completed_at is not None

    def test_add_event(self) -> None:
        store = TaskStore()
        task = store.create(TaskType.EXECUTE_CAD)
        store.add_event(task.id, {"event": "status", "data": {"message": "starting"}})
        assert len(task.events) == 1
        assert task.events[0]["event"] == "status"

    def test_add_artifact(self) -> None:
        store = TaskStore()
        task = store.create(TaskType.EXECUTE_CAD)
        store.add_artifact(task.id, "model.stl", "/tmp/model.stl")
        assert task.artifacts["model.stl"] == "/tmp/model.stl"

    def test_set_result(self) -> None:
        store = TaskStore()
        task = store.create(TaskType.EXECUTE_CAD)
        store.set_result(task.id, {"success": True, "output_path": "/tmp/out.stl"})
        assert task.result is not None
        assert task.result["success"] is True

    def test_set_error(self) -> None:
        store = TaskStore()
        task = store.create(TaskType.EXECUTE_CAD)
        store.set_error(task.id, "Something went wrong")
        assert task.error == "Something went wrong"

    def test_list_all(self) -> None:
        store = TaskStore()
        store.create(TaskType.EXECUTE_CAD, "task 1")
        store.create(TaskType.ANALYZE_MESH, "task 2")
        all_tasks = store.list_all()
        assert len(all_tasks) == 2


class TestTaskModel:
    """Test the task model."""

    def test_default_values(self) -> None:
        task = TaskModel(type=TaskType.EXECUTE_CAD)
        assert len(task.id) == 12
        assert task.status == TaskStatus.PENDING
        assert task.prompt == ""
        assert task.artifacts == {}
        assert task.events == []
        assert task.result is None
        assert task.error is None
        assert task.created_at is not None
        assert task.started_at is None
        assert task.completed_at is None

    def test_task_type_values(self) -> None:
        assert TaskType.EXECUTE_CAD.value == "execute_cad"
        assert TaskType.ANALYZE_MESH.value == "analyze_mesh"
        assert TaskType.DESIGN_PIPELINE.value == "design_pipeline"
        assert TaskType.CAD_SUBAGENT.value == "cad_subagent"

    def test_task_status_values(self) -> None:
        assert TaskStatus.PENDING.value == "pending"
        assert TaskStatus.RUNNING.value == "running"
        assert TaskStatus.COMPLETED.value == "completed"
        assert TaskStatus.FAILED.value == "failed"
