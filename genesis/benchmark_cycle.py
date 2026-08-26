from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any

from .benchmark_execution import BenchmarkExecutionPlanner
from .github_issue_task_router import issue_authority_enabled, issue_backed, route_unbacked_tasks
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
    """Return True only when a paused measurement has a new reason to run."""
    del queue
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
        if benchmark_id == "agents_last_exam":
            return False
        readiness = planner._execution_readiness(benchmark_id)
        return bool(readiness.get("ready", False))

    return False


def candidate_tasks(
    queue: PersistentTaskQueue,
    planner: BenchmarkExecutionPlanner | None = None,
    *,
    require_issue: bool = False,
):
    candidates = []
    for task in queue.list(limit=200):
        if require_issue and not issue_backed(task):
            continue
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
    """Advance at most one Issue-backed durable frontier benchmark task in production.

    GitHub Issues are authoritative in the real Genesis runtime; SQLite is
    execution/cache state only. Benchmark work is therefore routed to an Issue
    before it may run. Temporary unit-test roots retain isolated behavior without
    mutating the real repository. The planner never invents scores or changes
    validation/promotion authority.
    """
    root = Path(root).resolve()
    queue = PersistentTaskQueue(root / "runtime" / "genesis_tasks.sqlite3")
    authority = issue_authority_enabled(root)
    issue_sync = route_unbacked_tasks(root)
    planner = BenchmarkExecutionPlanner(root)
    candidates = candidate_tasks(queue, planner, require_issue=authority)
    if not candidates:
        unbacked = [
            task.task_id for task in queue.list(limit=200)
            if authority
            and not issue_backed(task)
            and task.module_id == "genesis.evaluation"
            and task.payload.get("task_type") == "frontier_benchmark_measurement"
            and task.state in {"new", "assigned", "blocked", "failed", "paused"}
        ]
        return {
            "status": "waiting_for_github_issue" if unbacked else "idle",
            "reason": "no_issue_backed_executable_benchmark_evaluation_task" if authority else "no executable benchmark evaluation task",
            "unbacked_task_ids": unbacked,
            "github_issue_authority_enforced": authority,
            "github_issue_sync": issue_sync,
        }

    task = candidates[0]
    if task.state == "paused":
        task = queue.resume(task.task_id, module_id="genesis.evaluation")
    elif task.state in {"new", "blocked", "failed"}:
        if task.state == "failed" and not queue.retryable(task):
            return {
                "status": "not_retryable",
                "task": asdict(task),
                "github_issue_authority_enforced": authority,
                "github_issue_sync": issue_sync,
            }
        task = queue.transition(task.task_id, "assigned", module_id="genesis.evaluation")

    if authority and not issue_backed(task):
        raise RuntimeError("GitHub Issue is required before benchmark execution")

    task = queue.transition(task.task_id, "running", module_id="genesis.evaluation")
    result = planner.advance(task)
    if result["status"] == "evidence_staged":
        queue.transition(task.task_id, "review", module_id="genesis.evaluation")
    elif result["status"] == "runner_work_queued":
        queue.pause(
            task.task_id,
            f"Waiting for benchmark runner task {result['task_id']} generation {result.get('work_generation', 1)} to produce real comparable evidence",
        )
        if authority:
            route_unbacked_tasks(root)
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
    return {
        "status": result["status"],
        "task_id": task.task_id,
        "github_issue_number": int(task.payload.get("github_issue_number") or 0),
        "result": result,
        "github_issue_authority_enforced": authority,
        "github_issue_sync": issue_sync,
    }
