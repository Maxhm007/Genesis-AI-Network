from __future__ import annotations

import json
from pathlib import Path

from genesis.benchmark_cycle import advance_one_benchmark
from genesis.deterministic_benchmark_builder import DeterministicBenchmarkIntegrationProvider
from genesis.modules.task_queue import PersistentTaskQueue


RECOVERABLE_PROVIDER_PAUSE = "waiting_for_non_qwen_coding_provider"
BENCHMARK_RUNNER_TASK_TYPE = "benchmark_runner_integration"


def _resume_deterministic_benchmark_runner(root: Path) -> dict | None:
    """Resume only provider-paused runner work now covered by a deterministic template.

    A benchmark runner may have been durably paused before Genesis learned a safe,
    provider-independent implementation path. Do not make arbitrary paused work
    executable: the pause reason and benchmark template must both match exactly.
    """
    queue = PersistentTaskQueue(root / "runtime" / "genesis_tasks.sqlite3")
    candidates = [
        task
        for task in queue.list(limit=5000)
        if task.payload.get("task_type") == BENCHMARK_RUNNER_TASK_TYPE
        and task.state == "paused"
        and task.state_reason == RECOVERABLE_PROVIDER_PAUSE
        and str(task.payload.get("benchmark_id") or "").strip()
        == DeterministicBenchmarkIntegrationProvider.BENCHMARK_ID
    ]
    if not candidates:
        return None

    candidates.sort(key=lambda task: (-task.priority, task.created_at, task.task_id))
    task = candidates[0]
    resumed = queue.resume(task.task_id, module_id=task.module_id or "genesis.coding")
    return {
        "status": "deterministic_runner_resumed",
        "task_id": resumed.task_id,
        "benchmark_id": str(resumed.payload.get("benchmark_id") or ""),
        "from_state": "paused",
        "state": resumed.state,
        "reason": RECOVERABLE_PROVIDER_PAUSE,
    }


def _recover_running_benchmark(root: Path, error: str) -> dict:
    queue = PersistentTaskQueue(root / "runtime" / "genesis_tasks.sqlite3")
    running = [
        task
        for task in queue.list(limit=200)
        if task.module_id == "genesis.evaluation"
        and task.payload.get("task_type") == "frontier_benchmark_measurement"
        and task.state == "running"
    ]
    if not running:
        return {"status": "worker_error", "error": error}

    task = running[0]
    recovered = queue.record_failure(
        task.task_id,
        error,
        classification="evaluation_worker",
        retry_after_seconds=0,
        module_id="genesis.evaluation",
    )
    return {
        "status": "worker_error_recovered",
        "task_id": task.task_id,
        "task_state": recovered.state,
        "error": error,
    }


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    runner_recovery = _resume_deterministic_benchmark_runner(root)
    try:
        result = advance_one_benchmark(root)
    except Exception as exc:
        result = _recover_running_benchmark(
            root,
            f"benchmark_worker_error:{type(exc).__name__}:{exc}"[:2000],
        )
    if runner_recovery is not None:
        result = dict(result)
        result["runner_recovery"] = runner_recovery
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
