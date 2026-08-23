from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any

from .benchmark_execution import BenchmarkExecutionPlanner
from .modules.task_queue import GenesisTask, PersistentTaskQueue


_STATE_PRIORITY = {
    "assigned": 0,
    "new": 1,
    "blocked": 2,
    "failed": 3,
    "paused": 4,
}

OWNER_EXTERNAL_PREFIX = "External owner authority required for real benchmark execution:"
NON_OWNER_EXTERNAL_PREFIX = "External benchmark evidence required for real benchmark execution:"
LEGACY_EXTERNAL_PREFIX = "External authority required for real benchmark execution:"
RUNNER_WAIT_PREFIX = "Waiting for benchmark runner task "
RUNNER_EXHAUSTED_PREFIX = "Bounded benchmark runner integration is exhausted."


def _benchmark_id(task: GenesisTask) -> str:
    benchmark = task.payload.get("benchmark", {}) if isinstance(task.payload, dict) else {}
    return str(benchmark.get("benchmark_id", "")).strip()


def _paused_task_ready(
    task: GenesisTask,
    queue: PersistentTaskQueue,
    planner: BenchmarkExecutionPlanner,
) -> bool:
    """Return True only when a paused measurement has a new reason to run.

    Paused benchmark work used to be retried every cycle. A durable external blocker
    could therefore monopolize the single bounded benchmark slot and starve other
    benchmark families. Resume only when child work finished, prerequisites changed,
    evidence arrived, or a newly expanded bounded integration budget permits a new
    strategy generation.
    """
    reason = str(task.state_reason or "")
    benchmark_id = _benchmark_id(task)
    if not benchmark_id:
        return False

    input_path = planner.input_dir / f"{benchmark_id}.json"
    if input_path.is_file():
        return True

    if reason.startswith(RUNNER_WAIT_PREFIX):
        runner_tasks = planner._runner_tasks(benchmark_id)
        if not runner_tasks:
            return True
        latest = max(runner_tasks, key=planner._runner_generation)
        return latest.state in planner.TERMINAL_RUNNER_STATES

    if reason.startswith(RUNNER_EXHAUSTED_PREFIX):
        runner_tasks = planner._runner_tasks(benchmark_id)
        if not runner_tasks:
            return True
        latest = max(runner_tasks, key=planner._runner_generation)
        return planner._runner_generation(latest) < planner.MAX_RUNNER_INTEGRATION_GENERATIONS

    if reason.startswith((OWNER_EXTERNAL_PREFIX, NON_OWNER_EXTERNAL_PREFIX, LEGACY_EXTERNAL_PREFIX)):
        # ALE is already adapter-ready; only a newly staged official run changes its
        # state. Treating adapter readiness itself as progress would re-run the same
        # blocker forever.
        if benchmark_id == "agents_last_exam":
            return False
        readiness = planner._execution_readiness(benchmark_id)
        return bool(readiness.get("ready", False))

    return False


def candidate_tasks(
    queue: PersistentTaskQueue,
    planner: BenchmarkExecutionPlanner | None = None,
):
    candidates = []
    for task in queue.list(limit=200):
        if task.module_id != "genesis.evaluation":
            continue
        if task.payload.get("task_type") != "frontier_benchmark_measurement":
            continue
        if task.state in {"new", "assigned", "blocked"}:
            candidates.append(task)
            continue
        if task.state == "failed" and queue.retryable(task):
            candidates.append(task)
            continue
        if task.state == "paused" and planner is not None and _paused_task_ready(task, queue, planner):
            candidates.append(task)
    candidates.sort(key=lambda task: _STATE_PRIORITY.get(task.state, 99))
    return candidates


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
    candidates = candidate_tasks(queue, planner)
    if not candidates:
        return {"status": "idle", "reason": "no executable benchmark evaluation task"}

    task = candidates[0]
    if task.state in {"new", "blocked", "failed", "paused"}:
        if task.state == "failed" and not queue.retryable(task):
            return {"status": "not_retryable", "task": asdict(task)}
        if task.state == "paused":
            task = queue.resume(task.task_id)
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
    elif result["status"] == "runner_integration_exhausted":
        queue.pause(
            task.task_id,
            "Bounded benchmark runner integration is exhausted. "
            "Do not create another runner generation until benchmark-specific execution/evidence support changes.",
        )
    elif result["status"] == "external_execution_required":
        missing = ", ".join(result.get("missing", [])) or "external benchmark execution prerequisites"
        owner_required = bool(result.get("owner_action_required", False))
        prefix = OWNER_EXTERNAL_PREFIX if owner_required else NON_OWNER_EXTERNAL_PREFIX
        queue.pause(
            task.task_id,
            f"{prefix} {missing}. No score may change until validated evidence is staged.",
        )
    else:
        queue.record_failure(
            task.task_id,
            result.get("reason", "benchmark execution failed"),
            classification="evaluation",
        )
    return {"status": result["status"], "task_id": task.task_id, "result": result}
