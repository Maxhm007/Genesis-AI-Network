from __future__ import annotations

from pathlib import Path

from genesis.benchmark_execution import BenchmarkExecutionPlanner
from genesis.modules.task_queue import PersistentTaskQueue


def make_task(root: Path, benchmark_id: str = "terminal_bench_2_1"):
    queue = PersistentTaskQueue(root / "runtime" / "genesis_tasks.sqlite3")
    return queue.create(
        f"Measure {benchmark_id}",
        module_id="genesis.evaluation",
        priority=92,
        payload={
            "task_type": "frontier_benchmark_measurement",
            "benchmark": {"benchmark_id": benchmark_id},
        },
    )


def test_missing_real_result_creates_one_runner_task(tmp_path: Path) -> None:
    task = make_task(tmp_path)
    planner = BenchmarkExecutionPlanner(tmp_path)
    first = planner.advance(task)
    second = planner.advance(task)
    assert first["status"] == "runner_work_queued"
    assert first["created"] is True
    assert second["created"] is False
    assert first["task_id"] == second["task_id"]
    child = planner.queue.get(first["task_id"])
    assert child is not None
    assert child.module_id == "genesis.coding"
    assert child.payload["score_fabrication_forbidden"] is True
    assert "genesis/terminal_bench_evidence.py" in child.payload["context_paths"]


def test_unknown_benchmark_still_queues_bounded_runner_work(tmp_path: Path) -> None:
    task = make_task(tmp_path, "new_frontier_benchmark")
    result = BenchmarkExecutionPlanner(tmp_path).advance(task)
    assert result["status"] == "runner_work_queued"
    child = BenchmarkExecutionPlanner(tmp_path).queue.get(result["task_id"])
    assert child is not None
    assert child.payload["benchmark_id"] == "new_frontier_benchmark"
    assert child.payload["requires_independent_validation"] is True


def test_invalid_evaluation_task_does_not_create_work(tmp_path: Path) -> None:
    queue = PersistentTaskQueue(tmp_path / "runtime" / "genesis_tasks.sqlite3")
    task = queue.create("Measure something", module_id="genesis.evaluation", payload={})
    planner = BenchmarkExecutionPlanner(tmp_path)
    result = planner.advance(task)
    assert result["status"] == "invalid_task"
    assert len(planner.queue.list(limit=20)) == 1
