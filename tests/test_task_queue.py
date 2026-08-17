from pathlib import Path

import pytest

from genesis.modules.task_queue import PersistentTaskQueue


def test_task_survives_queue_reopen(tmp_path: Path):
    db = tmp_path / "tasks.sqlite3"
    queue = PersistentTaskQueue(db)
    task = queue.create("Research a bounded question", module_id="genesis.research", priority=80)
    queue.transition(task.task_id, "assigned")
    queue.transition(task.task_id, "running")

    reopened = PersistentTaskQueue(db)
    restored = reopened.get(task.task_id)
    assert restored is not None
    assert restored.state == "running"
    assert restored.module_id == "genesis.research"


def test_task_state_machine_rejects_invalid_jump(tmp_path: Path):
    queue = PersistentTaskQueue(tmp_path / "tasks.sqlite3")
    task = queue.create("Do work")
    with pytest.raises(ValueError, match="invalid transition"):
        queue.transition(task.task_id, "complete")


def test_create_unique_prevents_duplicate_scan_tasks(tmp_path: Path):
    queue = PersistentTaskQueue(tmp_path / "tasks.sqlite3")
    first, created_first = queue.create_unique("source:https://example.invalid/1", "Review finding", priority=90)
    second, created_second = queue.create_unique("source:https://example.invalid/1", "Review finding again", priority=90)
    assert created_first is True
    assert created_second is False
    assert first.task_id == second.task_id
    assert len(queue.list()) == 1


def test_running_task_can_be_paused_held_and_resumed_with_reason(tmp_path: Path):
    queue = PersistentTaskQueue(tmp_path / "tasks.sqlite3")
    task = queue.create("Long running research")
    queue.transition(task.task_id, "assigned")
    queue.transition(task.task_id, "running")

    paused = queue.hold(task.task_id, "Waiting for verified source data")
    assert paused.state == "paused"
    assert paused.state_reason == "Waiting for verified source data"

    resumed = queue.resume(task.task_id)
    assert resumed.state == "assigned"
    assert resumed.state_reason is None


def test_cancel_requires_explicit_reason_and_records_it(tmp_path: Path):
    queue = PersistentTaskQueue(tmp_path / "tasks.sqlite3")
    task = queue.create("Potentially obsolete task")
    queue.transition(task.task_id, "assigned")
    queue.transition(task.task_id, "running")

    with pytest.raises(ValueError, match="cancellation reason is required"):
        queue.cancel(task.task_id, "")
    with pytest.raises(ValueError, match="requires cancel"):
        queue.transition(task.task_id, "cancelled")

    cancelled = queue.cancel(task.task_id, "Superseded by verified owner-approved requirement")
    assert cancelled.state == "cancelled"
    assert cancelled.state_reason == "Superseded by verified owner-approved requirement"
