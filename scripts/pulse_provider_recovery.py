from __future__ import annotations

import argparse
import json
import os
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


def _queue(root: Path = ROOT) -> PersistentTaskQueue:
    return PersistentTaskQueue(Path(root) / "runtime" / "genesis_tasks.sqlite3")


def _coding_work(queue: PersistentTaskQueue) -> list[GenesisTask]:
    rows: list[GenesisTask] = []
    for task in queue.list(limit=5000):
        if task.module_id != "genesis.coding":
            continue
        if task.state in RUNNABLE_STATES:
            rows.append(task)
            continue
        if task.state == "paused" and str(task.state_reason or "") in PROVIDER_WAIT_REASONS:
            rows.append(task)
    rows.sort(key=lambda task: (-int(task.priority), task.created_at, task.task_id))
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
    }


def resume_one(root: Path = ROOT) -> dict:
    providers = _eligible_provider_names(root)
    if not providers:
        return {"status": "no_eligible_provider", "resumed": False}

    queue = _queue(root)
    candidates = [
        task
        for task in _coding_work(queue)
        if task.state == "paused" and str(task.state_reason or "") in PROVIDER_WAIT_REASONS
    ]
    if not candidates:
        return {"status": "nothing_to_resume", "resumed": False, "provider_names": providers}

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
