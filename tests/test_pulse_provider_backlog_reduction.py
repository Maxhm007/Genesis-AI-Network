from __future__ import annotations

from pathlib import Path

from genesis.modules.task_queue import PersistentTaskQueue
from scripts import pulse_provider_recovery as recovery


def _create(queue: PersistentTaskQueue, task_type: str, *, priority: int = 90, paused: bool = False):
    task = queue.create(
        f"Work on {task_type}",
        module_id="genesis.coding",
        priority=priority,
        payload={"task_type": task_type},
    )
    queue.transition(task.task_id, "assigned", module_id="genesis.coding")
    if paused:
        return queue.pause(task.task_id, "waiting_for_eligible_coding_provider")
    return task


def _drain() -> dict:
    return {"active": True, "open_issue_count": 84, "high_water": 40}


def test_backlog_reduction_prevents_capability_growth_from_triggering_model_setup(monkeypatch, tmp_path: Path) -> None:
    queue = PersistentTaskQueue(tmp_path / "runtime" / "genesis_tasks.sqlite3")
    growth = _create(queue, "capability_growth", priority=95)

    monkeypatch.setattr(recovery, "_drain_context", _drain)
    monkeypatch.setattr(recovery, "_eligible_provider_names", lambda root=tmp_path: [])

    result = recovery.inspect(tmp_path)

    assert result["status"] == "idle_backlog_reduction"
    assert result["needs_local_provider"] is False
    assert result["coding_work_count"] == 0
    assert result["next_task_id"] is None
    assert result["backlog_reduction"]["active"] is True
    assert result["backlog_reduction"]["suppressed_task_ids"] == [growth.task_id]
    assert result["priority_rebalance"]["status"] == "deferred_backlog_reduction"


def test_repair_coding_still_bypasses_backlog_reduction(monkeypatch, tmp_path: Path) -> None:
    queue = PersistentTaskQueue(tmp_path / "runtime" / "genesis_tasks.sqlite3")
    growth = _create(queue, "capability_growth", priority=99)
    repair = _create(queue, "self_repair", priority=80)

    monkeypatch.setattr(recovery, "_drain_context", _drain)
    monkeypatch.setattr(recovery, "_eligible_provider_names", lambda root=tmp_path: [])

    result = recovery.inspect(tmp_path)

    assert result["status"] == "provider_needed"
    assert result["needs_local_provider"] is True
    assert result["coding_work_count"] == 1
    assert result["next_task_id"] == repair.task_id
    assert result["next_task_type"] == "self_repair"
    assert result["backlog_reduction"]["suppressed_task_ids"] == [growth.task_id]


def test_resume_one_skips_paused_growth_and_resumes_repair_during_drain(monkeypatch, tmp_path: Path) -> None:
    queue = PersistentTaskQueue(tmp_path / "runtime" / "genesis_tasks.sqlite3")
    growth = _create(queue, "capability_growth", priority=99, paused=True)
    repair = _create(queue, "issue_repair", priority=80, paused=True)

    monkeypatch.setattr(recovery, "_drain_context", _drain)
    monkeypatch.setattr(recovery, "_eligible_provider_names", lambda root=tmp_path: ["qwen-test-provider"])

    result = recovery.resume_one(tmp_path)

    assert result["status"] == "provider_wait_resumed"
    assert result["task_id"] == repair.task_id
    assert queue.get(repair.task_id).state == "assigned"
    assert queue.get(growth.task_id).state == "paused"
