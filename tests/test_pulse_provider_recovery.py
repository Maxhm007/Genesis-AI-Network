from __future__ import annotations

from pathlib import Path

from genesis.modules.task_queue import PersistentTaskQueue
from scripts.pulse_provider_recovery import PROVIDER_WAIT_REASONS, _coding_work, resume_one


class AvailableProvider:
    name = "qwen-test-provider"

    def available(self) -> bool:
        return True

    def reason(self, prompt: str) -> str:
        return "{}"


def _pause(queue: PersistentTaskQueue, *, task_type: str, priority: int, reason: str):
    task = queue.create(
        f"Work on {task_type}",
        module_id="genesis.coding",
        priority=priority,
        payload={"task_type": task_type},
    )
    queue.transition(task.task_id, "assigned", module_id="genesis.coding")
    return queue.pause(task.task_id, reason)


def test_coding_work_includes_legacy_and_provider_neutral_waits(tmp_path: Path) -> None:
    queue = PersistentTaskQueue(tmp_path / "runtime" / "genesis_tasks.sqlite3")
    legacy, neutral = sorted(PROVIDER_WAIT_REASONS)
    first = _pause(queue, task_type="benchmark_runner_integration", priority=93, reason=legacy)
    second = _pause(queue, task_type="capability_growth", priority=95, reason=neutral)
    unrelated = _pause(queue, task_type="other", priority=100, reason="external_execution_required")

    work = _coding_work(queue)

    assert [task.task_id for task in work] == [second.task_id, first.task_id]
    assert unrelated.task_id not in {task.task_id for task in work}


def test_resume_one_prefers_highest_priority_provider_wait(monkeypatch, tmp_path: Path) -> None:
    queue = PersistentTaskQueue(tmp_path / "runtime" / "genesis_tasks.sqlite3")
    legacy = "waiting_for_non_qwen_coding_provider"
    runner = _pause(queue, task_type="benchmark_runner_integration", priority=93, reason=legacy)
    growth = _pause(queue, task_type="capability_growth", priority=95, reason=legacy)

    monkeypatch.setattr(
        "scripts.pulse_provider_recovery._eligible_provider_names",
        lambda root=tmp_path: ["qwen-test-provider"],
    )
    result = resume_one(tmp_path)

    assert result["status"] == "provider_wait_resumed"
    assert result["task_id"] == growth.task_id
    assert queue.get(growth.task_id).state == "assigned"
    assert queue.get(runner.task_id).state == "paused"


def test_resume_one_requires_real_eligible_provider(monkeypatch, tmp_path: Path) -> None:
    queue = PersistentTaskQueue(tmp_path / "runtime" / "genesis_tasks.sqlite3")
    task = _pause(
        queue,
        task_type="capability_growth",
        priority=95,
        reason="waiting_for_eligible_coding_provider",
    )
    monkeypatch.setattr(
        "scripts.pulse_provider_recovery._eligible_provider_names",
        lambda root=tmp_path: [],
    )

    result = resume_one(tmp_path)

    assert result["status"] == "no_eligible_provider"
    assert queue.get(task.task_id).state == "paused"
