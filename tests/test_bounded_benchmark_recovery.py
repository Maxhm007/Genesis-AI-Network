from __future__ import annotations

from genesis.benchmark_execution import BenchmarkExecutionPlanner
from genesis.modules.task_queue import PersistentTaskQueue
from genesis.task_lifecycle import TaskLifecycleReconciler


def test_blocked_benchmark_runner_consumes_retry_budget_and_quarantines(tmp_path):
    queue = PersistentTaskQueue(tmp_path / "runtime" / "genesis_tasks.sqlite3")
    task = queue.create(
        "Build benchmark runner",
        module_id="genesis.coding",
        priority=93,
        max_attempts=2,
        payload={"task_type": "benchmark_runner_integration", "benchmark_id": "terminal_bench_2_1"},
    )
    queue.transition(task.task_id, "assigned", module_id="genesis.coding")
    queue.transition(task.task_id, "running", module_id="genesis.coding")
    queue.transition(task.task_id, "blocked", module_id="genesis.coding")

    first = TaskLifecycleReconciler(tmp_path).reconcile()
    retried = queue.get(task.task_id)
    assert retried is not None
    assert retried.state == "assigned"
    assert retried.attempt_count == 1
    assert task.task_id in first["blocked_retried"]

    queue.transition(task.task_id, "running", module_id="genesis.coding")
    queue.transition(task.task_id, "blocked", module_id="genesis.coding")
    second = TaskLifecycleReconciler(tmp_path).reconcile()
    exhausted = queue.get(task.task_id)
    assert exhausted is not None
    assert exhausted.state == "quarantined"
    assert exhausted.attempt_count == 2
    assert task.task_id in second["blocked_quarantined"]


def test_benchmark_planner_creates_new_generation_after_quarantine(tmp_path):
    queue = PersistentTaskQueue(tmp_path / "runtime" / "genesis_tasks.sqlite3")
    parent = queue.create(
        "Measure Terminal-Bench",
        module_id="genesis.evaluation",
        priority=93,
        payload={
            "task_type": "frontier_benchmark_measurement",
            "benchmark": {"benchmark_id": "terminal_bench_2_1"},
        },
    )
    planner = BenchmarkExecutionPlanner(tmp_path)

    first = planner.advance(parent)
    assert first["status"] == "runner_work_queued"
    assert first["created"] is True
    assert first["work_generation"] == 1
    first_id = first["task_id"]

    queue.record_failure(first_id, "runner attempt 1 failed", retry_after_seconds=0)
    queue.record_failure(first_id, "runner attempt 2 failed", retry_after_seconds=0)
    queue.record_failure(first_id, "runner attempt 3 failed", retry_after_seconds=0)
    exhausted = queue.get(first_id)
    assert exhausted is not None
    assert exhausted.state == "quarantined"

    second = planner.advance(parent)
    assert second["status"] == "runner_work_queued"
    assert second["created"] is True
    assert second["work_generation"] == 2
    assert second["task_id"] != first_id
    successor = queue.get(second["task_id"])
    assert successor is not None
    assert successor.payload["work_generation"] == 2
    assert successor.payload["requires_independent_validation"] is True
    assert successor.payload["score_fabrication_forbidden"] is True
