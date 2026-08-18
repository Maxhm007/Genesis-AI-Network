from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from genesis.benchmark_execution import BenchmarkExecutionPlanner
from genesis.modules.task_queue import PersistentTaskQueue


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    queue = PersistentTaskQueue(root / "runtime" / "genesis_tasks.sqlite3")
    planner = BenchmarkExecutionPlanner(root)
    candidates = [
        task for task in queue.list(limit=200)
        if task.module_id == "genesis.evaluation"
        and task.payload.get("task_type") == "frontier_benchmark_measurement"
        and task.state in {"new", "assigned", "blocked", "failed"}
    ]
    if not candidates:
        print(json.dumps({"status": "idle", "reason": "no executable benchmark evaluation task"}, indent=2))
        return

    task = candidates[0]
    if task.state in {"new", "blocked", "failed"}:
        if task.state == "new":
            task = queue.transition(task.task_id, "assigned", module_id="genesis.evaluation")
        elif task.state == "blocked":
            task = queue.transition(task.task_id, "assigned", module_id="genesis.evaluation")
        elif task.state == "failed" and queue.retryable(task):
            task = queue.transition(task.task_id, "assigned", module_id="genesis.evaluation")
        else:
            print(json.dumps({"status": "not_retryable", "task": asdict(task)}, indent=2, sort_keys=True))
            return

    task = queue.transition(task.task_id, "running", module_id="genesis.evaluation")
    result = planner.advance(task)
    if result["status"] == "evidence_staged":
        queue.transition(task.task_id, "review", module_id="genesis.evaluation")
    elif result["status"] == "runner_work_queued":
        queue.pause(task.task_id, f"Waiting for benchmark runner task {result['task_id']} to produce real comparable evidence")
    else:
        queue.record_failure(task.task_id, result.get("reason", "benchmark execution failed"), classification="evaluation")
    print(json.dumps({"status": result["status"], "task_id": task.task_id, "result": result}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
