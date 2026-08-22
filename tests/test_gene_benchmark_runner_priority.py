from __future__ import annotations

from pathlib import Path

from genesis.modules.task_queue import PersistentTaskQueue
from scripts.gene_continuous_work import (
    _completion_poll_blocks_benchmark_runner,
    _next_benchmark_runner_task,
    _refresh_benchmark_runner_context,
)


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


def test_benchmark_runner_selection_prefers_highest_priority_within_work_state(tmp_path: Path) -> None:
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


def test_blocked_benchmark_runner_is_resumable(tmp_path: Path) -> None:
    queue = _queue(tmp_path)
    runner = queue.create(
        "Integrate agents_last_exam runner",
        module_id="genesis.coding",
        priority=93,
        payload={"task_type": "benchmark_runner_integration", "benchmark_id": "agents_last_exam"},
    )
    queue.transition(runner.task_id, "assigned", module_id="genesis.coding")
    queue.transition(runner.task_id, "running", module_id="genesis.coding")
    queue.transition(runner.task_id, "blocked", module_id="genesis.coding")

    selected = _next_benchmark_runner_task(queue)

    assert selected is not None
    assert selected.task_id == runner.task_id
    assert selected.state == "blocked"


def test_stale_benchmark_runner_context_is_refreshed_before_attempt(tmp_path: Path) -> None:
    queue = _queue(tmp_path)
    runner = queue.create(
        "Integrate agents_last_exam runner",
        module_id="genesis.coding",
        priority=93,
        payload={
            "task_type": "benchmark_runner_integration",
            "benchmark_id": "agents_last_exam",
            "context_paths": ["scripts/benchmark_task_worker.py"],
        },
    )

    refreshed = _refresh_benchmark_runner_context(runner)

    assert refreshed.task_id == runner.task_id
    assert refreshed.state == runner.state
    assert refreshed.payload["context_paths"][0] == "genesis/benchmark_execution.py"
    assert "scripts/benchmark_task_worker.py" not in refreshed.payload["context_paths"]
    assert runner.payload["context_paths"] == ["scripts/benchmark_task_worker.py"]


def test_runner_in_review_finishes_before_new_higher_priority_runner(tmp_path: Path) -> None:
    queue = _queue(tmp_path)
    review_runner = queue.create(
        "Review agents_last_exam runner",
        module_id="genesis.coding",
        priority=93,
        payload={"task_type": "benchmark_runner_integration", "benchmark_id": "agents_last_exam"},
    )
    queue.transition(review_runner.task_id, "assigned", module_id="genesis.coding")
    queue.transition(review_runner.task_id, "running", module_id="genesis.coding")
    queue.transition(review_runner.task_id, "review", module_id="genesis.coding")
    queue.create(
        "Integrate newer benchmark runner",
        module_id="genesis.coding",
        priority=100,
        payload={"task_type": "benchmark_runner_integration", "benchmark_id": "swe_bench_pro"},
    )

    selected = _next_benchmark_runner_task(queue)

    assert selected is not None
    assert selected.task_id == review_runner.task_id
    assert selected.state == "review"


def test_validation_wait_does_not_starve_benchmark_runner() -> None:
    assert _completion_poll_blocks_benchmark_runner(
        {"handled": True, "action": "pipeline_wait_validation"}
    ) is False
    assert _completion_poll_blocks_benchmark_runner(
        {"handled": True, "action": "pipeline_internal_review_approved"}
    ) is True


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
