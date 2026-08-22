from __future__ import annotations

from pathlib import Path

from genesis.modules.task_queue import PersistentTaskQueue
from scripts.gene_continuous_work import _next_benchmark_runner_task


def _queue(root: Path) -> PersistentTaskQueue:
    return PersistentTaskQueue(root / "runtime" / "genesis_tasks.sqlite3")


def test_benchmark_runner_is_selected_ahead_of_unrelated_work(tmp_path: Path) -> None:
    queue = _queue(tmp_path)
    queue.create(
        "Unrelated learning work",
        module_id="genesis.coding",
        priority=99,
        payload={"task_type": "new_capability", "context_paths": ["genesis/learned_capabilities.py"]},
    )
    runner = queue.create(
        "Integrate agents_last_exam runner",
        module_id="genesis.coding",
        priority=93,
        payload={
            "task_type": "benchmark_runner_integration",
            "benchmark_id": "agents_last_exam",
            "context_paths": ["genesis/benchmark_execution.py"],
        },
    )

    selected = _next_benchmark_runner_task(queue)

    assert selected is not None
    assert selected.task_id == runner.task_id
    assert selected.payload["benchmark_id"] == "agents_last_exam"


def test_benchmark_runner_selection_prefers_highest_priority_oldest(tmp_path: Path) -> None:
    queue = _queue(tmp_path)
    older = queue.create(
        "Integrate agents_last_exam runner",
        module_id="genesis.coding",
        priority=93,
        payload={"task_type": "benchmark_runner_integration", "benchmark_id": "agents_last_exam"},
    )
    newer = queue.create(
        "Integrate swe_bench_pro runner",
        module_id="genesis.coding",
        priority=94,
        payload={"task_type": "benchmark_runner_integration", "benchmark_id": "swe_bench_pro"},
    )

    selected = _next_benchmark_runner_task(queue)

    assert selected is not None
    assert selected.task_id == newer.task_id
    assert selected.task_id != older.task_id


def test_non_retryable_failed_runner_is_not_selected(tmp_path: Path) -> None:
    queue = _queue(tmp_path)
    runner = queue.create(
        "Integrate benchmark runner",
        module_id="genesis.coding",
        priority=93,
        max_attempts=1,
        payload={"task_type": "benchmark_runner_integration", "benchmark_id": "agents_last_exam"},
    )
    queue.transition(runner.task_id, "assigned", module_id="genesis.coding")
    queue.transition(runner.task_id, "running", module_id="genesis.coding")
    queue.record_failure(
        runner.task_id,
        "bounded failure",
        classification="pipeline_development",
        module_id="genesis.coding",
    )

    assert _next_benchmark_runner_task(queue) is None
