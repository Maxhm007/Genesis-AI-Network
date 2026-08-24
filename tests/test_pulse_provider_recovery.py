from __future__ import annotations

from pathlib import Path

from genesis.modules.task_queue import PersistentTaskQueue
from scripts.pulse_provider_recovery import (
    MEASURED_GROWTH_DEFER_REASON,
    PROVIDER_WAIT_REASONS,
    _coding_work,
    _rebalance_work_priority,
    resume_one,
)


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


def test_measured_capability_growth_outranks_higher_priority_speculative_coding(tmp_path: Path) -> None:
    queue = PersistentTaskQueue(tmp_path / "runtime" / "genesis_tasks.sqlite3")
    speculative = queue.create(
        "Speculative learned capability",
        module_id="genesis.coding",
        priority=100,
        payload={"task_type": "new_capability"},
    )
    growth = queue.create(
        "Improve measured software engineering deficit",
        module_id="genesis.coding",
        priority=95,
        payload={"task_type": "capability_growth"},
    )

    work = _coding_work(queue)

    assert work[0].task_id == growth.task_id
    assert speculative.task_id in {task.task_id for task in work[1:]}


def test_active_measured_growth_defers_benchmark_runner_until_growth_checkpoints(tmp_path: Path) -> None:
    queue = PersistentTaskQueue(tmp_path / "runtime" / "genesis_tasks.sqlite3")
    runner = queue.create(
        "Integrate next benchmark runner",
        module_id="genesis.coding",
        priority=99,
        payload={"task_type": "benchmark_runner_integration", "benchmark_id": "agents_last_exam"},
    )
    growth = queue.create(
        "Improve measured SWE-Bench deficit",
        module_id="genesis.coding",
        priority=95,
        payload={"task_type": "capability_growth", "benchmark_id": "swe_bench_pro"},
    )
    queue.transition(growth.task_id, "assigned", module_id="genesis.coding")

    first = _rebalance_work_priority(queue)

    deferred = queue.get(runner.task_id)
    assert deferred is not None
    assert deferred.state == "paused"
    assert deferred.state_reason == MEASURED_GROWTH_DEFER_REASON
    assert first["active_growth_task_ids"] == [growth.task_id]
    assert runner.task_id in first["deferred_benchmark_runner_ids"]

    queue.transition(growth.task_id, "running", module_id="genesis.coding")
    queue.transition(growth.task_id, "review", module_id="genesis.coding")
    second = _rebalance_work_priority(queue)

    resumed = queue.get(runner.task_id)
    assert resumed is not None
    assert resumed.state == "assigned"
    assert second["resumed_benchmark_runner_id"] == runner.task_id


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
