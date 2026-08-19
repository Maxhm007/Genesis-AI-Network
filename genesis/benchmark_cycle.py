from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any

from .benchmark_execution import BenchmarkExecutionPlanner
from .modules.task_queue import PersistentTaskQueue


def candidate_tasks(queue: PersistentTaskQueue):
    return [
        task
        for task in queue.list(limit=200)
        if task.module_id == "genesis.evaluation"
        and task.payload.get("task_type") == "frontier_benchmark_measurement"
        and (
            task.state in {"new", "assigned", "blocked", "paused"}
            or (task.state == "failed" and queue.retryable(task))
        )
    ]


def advance_one_benchmark(root: Path) -> dict[str, Any]:
    """Advance at most one durable frontier benchmark evaluation task.

    This is intentionally bounded and reuses the persistent Genesis task queue. It
    may queue validated runner-integration work, stage real benchmark evidence, or
    surface an external execution blocker. It never invents benchmark scores and it
    never changes validation or promotion authority.
    """
    root = Path(root).resolve()
    queue = PersistentTaskQueue(root / "runtime" / "genesis_tasks.sqlite3")
    planner = BenchmarkExecutionPlanner(root)
    candidates = candidate_tasks(queue)
    if not candidates:
        return {"status": "idle", "reason": "no executable benchmark evaluation task"}

    task = candidates[0]
    if task.state in {"new", "blocked", "failed"}:
        if task.state == "failed" and not queue.retryable(task):
            return {"status": "not_retryable", "task": asdict(task)}
        task = queue.transition(task.task_id, "assigned", module_id="genesis.evaluation")

    task = queue.transition(task.task_id, "running", module_id="genesis.evaluation")
    result = planner.advance(task)
    if result["status"] == "evidence_staged":
        queue.transition(task.task_id, "review", module_id="genesis.evaluation")
    elif result["status"] == "runner_work_queued":
        queue.pause(
            task.task_id,
            f"Waiting for benchmark runner task {result['task_id']} generation {result.get('work_generation', 1)} to produce real comparable evidence",
        )
    elif result["status"] == "external_execution_required":
        missing = ", ".join(result.get("missing", [])) or "external benchmark execution prerequisites"
        queue.pause(
            task.task_id,
            f"External authority required for real benchmark execution: {missing}. No score may change until validated evidence is staged.",
        )
    else:
        queue.record_failure(
            task.task_id,
            result.get("reason", "benchmark execution failed"),
            classification="evaluation",
        )
    return {"status": result["status"], "task_id": task.task_id, "result": result}
