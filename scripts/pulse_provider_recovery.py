from __future__ import annotations

import argparse
import json
from pathlib import Path

from genesis.intelligence_router import IntelligenceRouter
from genesis.issue_backpressure import (
    backlog_reduction_active,
    capacity_limited_task,
    configured_backlog_reduction_high_water,
    github_open_issue_count,
)
from genesis.modules.task_queue import GenesisTask, PersistentTaskQueue
from genesis.providers import ProviderRegistry


ROOT = Path(__file__).resolve().parents[1]
PROVIDER_WAIT_REASONS = {
    "waiting_for_non_qwen_coding_provider",  # legacy durable state
    "waiting_for_eligible_coding_provider",
}
# A blocked task is a durable checkpoint, not executable work. Treating it as
# runnable causes the same unchanged task to be delegated on every Gene Pulse.
# The component that clears the blocker must explicitly move it back to assigned.
RUNNABLE_STATES = {"new", "assigned"}
MEASURED_GROWTH_DEFER_REASON = "deferred_for_measured_capability_growth"


def _queue(root: Path = ROOT) -> PersistentTaskQueue:
    return PersistentTaskQueue(Path(root) / "runtime" / "genesis_tasks.sqlite3")


def _growth_is_executable(queue: PersistentTaskQueue, task: GenesisTask) -> bool:
    if task.payload.get("task_type") != "capability_growth":
        return False
    if task.state in {"new", "assigned", "running"}:
        return True
    if task.state == "failed":
        return queue.retryable(task)
    return task.state == "paused" and str(task.state_reason or "") in PROVIDER_WAIT_REASONS


def _active_measured_growth(queue: PersistentTaskQueue) -> list[GenesisTask]:
    rows = [task for task in queue.list(limit=5000) if _growth_is_executable(queue, task)]
    rows.sort(key=lambda task: (-int(task.priority), task.created_at, task.task_id))
    return rows


def _rebalance_work_priority(queue: PersistentTaskQueue) -> dict:
    """Prevent benchmark plumbing from starving measured capability improvement."""
    growth = _active_measured_growth(queue)
    deferred: list[str] = []
    resumed: str | None = None

    if growth:
        for task in queue.list(limit=5000):
            if task.payload.get("task_type") != "benchmark_runner_integration":
                continue
            if task.state not in {"new", "assigned", "running", "blocked", "failed"}:
                continue
            if task.state == "failed" and not queue.retryable(task):
                continue
            paused = queue.pause(task.task_id, MEASURED_GROWTH_DEFER_REASON)
            deferred.append(paused.task_id)
    else:
        candidates = [
            task
            for task in queue.list(limit=5000)
            if task.payload.get("task_type") == "benchmark_runner_integration"
            and task.state == "paused"
            and str(task.state_reason or "") == MEASURED_GROWTH_DEFER_REASON
        ]
        candidates.sort(key=lambda task: (-int(task.priority), task.created_at, task.task_id))
        if candidates:
            task = candidates[0]
            resumed_task = queue.resume(task.task_id, module_id=task.module_id or "genesis.coding")
            resumed = resumed_task.task_id

    return {
        "active_growth_task_ids": [task.task_id for task in growth],
        "deferred_benchmark_runner_ids": deferred,
        "resumed_benchmark_runner_id": resumed,
    }


def _coding_owned_work(task: GenesisTask) -> bool:
    """Return work that needs a coding-capable provider, regardless of queue owner."""
    return bool(
        task.module_id == "genesis.coding"
        or task.payload.get("task_type") == "capability_growth"
    )


def _coding_work(queue: PersistentTaskQueue) -> list[GenesisTask]:
    rows: list[GenesisTask] = []
    for task in queue.list(limit=5000):
        if not _coding_owned_work(task):
            continue
        if task.state in RUNNABLE_STATES:
            rows.append(task)
            continue
        if task.state == "failed" and queue.retryable(task):
            rows.append(task)
            continue
        if task.state == "paused" and str(task.state_reason or "") in PROVIDER_WAIT_REASONS:
            rows.append(task)
    rows.sort(
        key=lambda task: (
            0 if task.payload.get("task_type") == "capability_growth" else 1,
            -int(task.priority),
            task.created_at,
            task.task_id,
        )
    )
    return rows


def _eligible_provider_names(root: Path = ROOT) -> list[str]:
    registry = ProviderRegistry(root=Path(root))
    names: list[str] = []
    for provider in registry.available_providers():
        profile = IntelligenceRouter.profile(provider)
        if profile.name == "genesis-bootstrap":
            continue
        if "coding" not in profile.capabilities and "reasoning" not in profile.capabilities:
            continue
        names.append(profile.name)
    return names


def _drain_context() -> dict:
    open_issue_count = github_open_issue_count()
    high_water = configured_backlog_reduction_high_water()
    return {
        "active": backlog_reduction_active(open_issue_count, high_water=high_water),
        "open_issue_count": open_issue_count,
        "high_water": high_water,
    }


def _apply_backlog_reduction(work: list[GenesisTask], drain: dict) -> tuple[list[GenesisTask], list[GenesisTask]]:
    if not drain.get("active"):
        return list(work), []
    runnable = [task for task in work if not capacity_limited_task(task)]
    suppressed = [task for task in work if capacity_limited_task(task)]
    return runnable, suppressed


def inspect(root: Path = ROOT) -> dict:
    queue = _queue(root)
    drain = _drain_context()
    if drain["active"]:
        # Do not mutate benchmark/growth priority while the repository is in drain
        # mode. Those tasks remain durable but cannot trigger model provisioning.
        priority = {
            "active_growth_task_ids": [],
            "deferred_benchmark_runner_ids": [],
            "resumed_benchmark_runner_id": None,
            "status": "deferred_backlog_reduction",
        }
    else:
        priority = _rebalance_work_priority(queue)
    all_work = _coding_work(queue)
    work, suppressed = _apply_backlog_reduction(all_work, drain)
    providers = _eligible_provider_names(root)
    status = "provider_ready" if providers and work else ("provider_needed" if work else "idle")
    if drain["active"] and not work and suppressed:
        status = "idle_backlog_reduction"
    return {
        "status": status,
        "needs_local_provider": bool(work and not providers),
        "coding_work_count": len(work),
        "provider_names": providers,
        "next_task_id": work[0].task_id if work else None,
        "next_task_type": work[0].payload.get("task_type") if work else None,
        "next_task_priority": work[0].priority if work else None,
        "priority_rebalance": priority,
        "backlog_reduction": {
            **drain,
            "suppressed_task_ids": [task.task_id for task in suppressed],
            "suppressed_task_types": [str(task.payload.get("task_type") or "") for task in suppressed],
        },
    }


def resume_one(root: Path = ROOT) -> dict:
    providers = _eligible_provider_names(root)
    drain = _drain_context()
    if not providers:
        return {"status": "no_eligible_provider", "resumed": False, "backlog_reduction": drain}

    queue = _queue(root)
    if drain["active"]:
        priority = {
            "active_growth_task_ids": [],
            "deferred_benchmark_runner_ids": [],
            "resumed_benchmark_runner_id": None,
            "status": "deferred_backlog_reduction",
        }
    else:
        priority = _rebalance_work_priority(queue)
    all_candidates = [
        task
        for task in _coding_work(queue)
        if task.state == "paused" and str(task.state_reason or "") in PROVIDER_WAIT_REASONS
    ]
    candidates, suppressed = _apply_backlog_reduction(all_candidates, drain)
    if not candidates:
        return {
            "status": "nothing_to_resume_backlog_reduction" if suppressed else "nothing_to_resume",
            "resumed": False,
            "provider_names": providers,
            "priority_rebalance": priority,
            "backlog_reduction": {
                **drain,
                "suppressed_task_ids": [task.task_id for task in suppressed],
            },
        }

    task = candidates[0]
    resumed = queue.resume(task.task_id, module_id=task.module_id or "genesis.coding")
    return {
        "status": "provider_wait_resumed",
        "resumed": True,
        "task_id": resumed.task_id,
        "task_type": resumed.payload.get("task_type"),
        "priority": resumed.priority,
        "provider_names": providers,
        "previous_reason": task.state_reason,
        "state": resumed.state,
        "priority_rebalance": priority,
        "backlog_reduction": drain,
    }


def _write_github_output(path: str, payload: dict) -> None:
    with open(path, "a", encoding="utf-8") as handle:
        handle.write("needs_local_provider=" + ("true" if payload.get("needs_local_provider") else "false") + "\n")
        handle.write("coding_work_count=" + str(payload.get("coding_work_count", 0)) + "\n")
        handle.write("next_task_id=" + str(payload.get("next_task_id") or "") + "\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("inspect", "resume-one"))
    parser.add_argument("--github-output", default="")
    args = parser.parse_args()

    result = inspect(ROOT) if args.command == "inspect" else resume_one(ROOT)
    if args.github_output:
        _write_github_output(args.github_output, result)
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
