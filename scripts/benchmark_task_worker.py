from __future__ import annotations

import json
from pathlib import Path

from genesis.benchmark_cycle import advance_one_benchmark
from genesis.modules.task_queue import PersistentTaskQueue


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
    try:
        result = advance_one_benchmark(root)
    except Exception as exc:
        result = _recover_running_benchmark(
            root,
            f"benchmark_worker_error:{type(exc).__name__}:{exc}"[:2000],
        )
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
