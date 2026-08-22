from __future__ import annotations

from pathlib import Path

from genesis.modules.task_queue import PersistentTaskQueue
from scripts.benchmark_task_worker import (
    RECOVERABLE_PROVIDER_PAUSE,
    _resume_deterministic_benchmark_runner,
)


def _queue(root: Path) -> PersistentTaskQueue:
    return PersistentTaskQueue(root / "runtime" / "genesis_tasks.sqlite3")


def _paused_runner(
    root: Path,
    *,
    benchmark_id: str = "agents_last_exam",
    reason: str = RECOVERABLE_PROVIDER_PAUSE,
):
    queue = _queue(root)
    task = queue.create(
        f"Integrate {benchmark_id} runner",
        module_id="genesis.coding",
        priority=93,
        payload={
            "task_type": "benchmark_runner_integration",
            "benchmark_id": benchmark_id,
            "context_paths": ["genesis/benchmark_execution.py"],
        },
    )
    queue.transition(task.task_id, "assigned", module_id="genesis.coding")
    return queue.pause(task.task_id, reason)


def test_provider_paused_ale_runner_resumes_for_deterministic_template(tmp_path: Path) -> None:
    paused = _paused_runner(tmp_path)

    result = _resume_deterministic_benchmark_runner(tmp_path)

    assert result is not None
    assert result["status"] == "deterministic_runner_resumed"
    assert result["task_id"] == paused.task_id
    assert result["benchmark_id"] == "agents_last_exam"
    resumed = _queue(tmp_path).get(paused.task_id)
    assert resumed is not None
    assert resumed.state == "assigned"
    assert resumed.state_reason is None


def test_unrelated_pause_reason_is_not_resumed(tmp_path: Path) -> None:
    paused = _paused_runner(tmp_path, reason="external_execution_required")

    assert _resume_deterministic_benchmark_runner(tmp_path) is None
    current = _queue(tmp_path).get(paused.task_id)
    assert current is not None
    assert current.state == "paused"
    assert current.state_reason == "external_execution_required"


def test_unsupported_benchmark_is_not_resumed(tmp_path: Path) -> None:
    paused = _paused_runner(tmp_path, benchmark_id="swe_bench_pro")

    assert _resume_deterministic_benchmark_runner(tmp_path) is None
    current = _queue(tmp_path).get(paused.task_id)
    assert current is not None
    assert current.state == "paused"
    assert current.state_reason == RECOVERABLE_PROVIDER_PAUSE
