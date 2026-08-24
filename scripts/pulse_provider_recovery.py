from __future__ import annotations

import argparse
import json
from pathlib import Path

from genesis.intelligence_router import IntelligenceRouter
from genesis.modules.task_queue import GenesisTask, PersistentTaskQueue
from genesis.providers import ProviderRegistry


ROOT = Path(__file__).resolve().parents[1]
PROVIDER_WAIT_REASONS = {
    "waiting_for_non_qwen_coding_provider",  # legacy durable state
    "waiting_for_eligible_coding_provider",
}
RUNNABLE_STATES = {"new", "assigned", "blocked"}
MEASURED_GROWTH_DEFER_REASON = "deferred_for_measured_capability_growth"


def _queue(root: Path = ROOT) -> PersistentTaskQueue:
    return PersistentTaskQueue(Path(root) / "runtime" / "genesis_tasks.sqlite3")


def _growth_is_executable(queue: PersistentTaskQueue, task: GenesisTask) -> bool:
    if task.payload.get("task_type") != "capability_growth":
        return False
    if task.state in {"new", "assigned", "running", "blocked"}:
        return True
    if task.state == "failed":
        return queue.retryable(task)
    return task.state == "paused" and str(task.state_reason or "") in PROVIDER_WAIT_REASONS


def _active_measured_growth(queue: PersistentTaskQueue) -> list[GenesisTask]:
    rows = [task for task in queue.list(limit=5000) if _growth_is_executable(queue, task)]
    rows.sort(key=lambda task: (-int(task.priority), task.created_at, task.task_id))
    return rows


def _rebalance_work_priority(queue: PersistentTaskQueue) -> dict:
    """Prevent benchmark plumbing from starving measured capability improvement.

    A validated below-reference benchmark creates capability_growth work. While that
    work is executable (or merely waiting for the coding provider), benchmark runner
    integration stays durable but paused. As soon as no executable measured growth
    remains, one deferred runner is resumed so benchmark coverage continues.
    """
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
    """Return work that needs a coding-capable provider, regardless of queue owner.

    Capability-growth tasks are owned by ``genesis.improvement`` after the
    improvement/merge split, but their bounded implementation still runs through
    the coding worker. Filtering only on ``module_id == genesis.coding`` makes a
    measured benchmark deficit invisible to the delegated coding pulse and lets
    speculative learning work take its slot.
    """
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


def inspect(root: Path = ROOT) -> dict:
    queue = _queue(root)
    priority = _rebalance_work_priority(queue)
    work = _coding_work(queue)
    providers = _eligible_provider_names(root)
    return {
        "status": "provider_ready" if providers else ("provider_needed" if work else "idle"),
        "needs_local_provider": bool(work and not providers),
        "coding_work_count": len(work),
        "provider_names": providers,
        "next_task_id": work[0].task_id if work else None,
        "next_task_type": work[0].payload.get("task_type") if work else None,
        "next_task_priority": work[0].priority if work else None,
        "priority_rebalance": priority,
    }


def resume_one(root: Path = ROOT) -> dict:
    providers = _eligible_provider_names(root)
    if not providers:
        return {"status": "no_eligible_provider", "resumed": False}

    queue = _queue(root)
    priority = _rebalance_work_priority(queue)
    candidates = [
        task
        for task in _coding_work(queue)
        if task.state == "paused" and str(task.state_reason or "") in PROVIDER_WAIT_REASONS
    ]
    if not candidates:
        return {
            "status": "nothing_to_resume",
            "resumed": False,
            "provider_names": providers,
            "priority_rebalance": priority,
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
