from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .modules.task_queue import GenesisTask, PersistentTaskQueue
from .self_improvement_issue_router import ROUTER_PAUSE_PREFIX, _is_source_self_improvement_task


EXECUTION_SOURCE = "github_self_improvement_issue"
TERMINAL_STATES = {"complete", "quarantined", "cancelled"}
IN_FLIGHT_STATES = {"running", "review"}


def _normalize(value: object) -> str:
    return " ".join(str(value or "").split()).strip().lower()


def problem_fingerprint(task: GenesisTask) -> str:
    """Return a stable fingerprint for one real self-improvement problem.

    Source task IDs are intentionally excluded so repeated detections of the same
    task type/objective/target collapse into one execution problem.
    """
    payload = dict(task.payload or {})
    material = {
        "task_type": _normalize(payload.get("task_type") or "self_improvement"),
        "objective": _normalize(task.objective),
        "target_path": _normalize(str(payload.get("target_path") or "").replace("\\", "/").lstrip("./")),
    }
    digest = hashlib.sha256(
        json.dumps(material, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()[:20]
    return f"self-improvement-problem:{digest}"


def _execution_tasks(queue: PersistentTaskQueue, source_task_id: str) -> list[GenesisTask]:
    rows = [
        task
        for task in queue.list(limit=5000)
        if str(task.payload.get("source_self_improvement_task_id") or "") == source_task_id
        and str(task.payload.get("source") or "") == EXECUTION_SOURCE
        and int(task.payload.get("github_issue_number") or 0) > 0
    ]
    rows.sort(key=lambda task: (task.created_at, task.task_id))
    return rows


def _active_source(task: GenesisTask, executions: list[GenesisTask]) -> bool:
    if task.state in TERMINAL_STATES:
        return False
    if task.state == "paused" and str(task.state_reason or "").startswith(ROUTER_PAUSE_PREFIX):
        if executions and all(row.state in TERMINAL_STATES for row in executions):
            return False
    return True


def _canonical_rank(task: GenesisTask, executions: list[GenesisTask]) -> tuple[int, str, str]:
    if any(row.state in IN_FLIGHT_STATES for row in executions):
        rank = 0
    elif any(row.state not in TERMINAL_STATES for row in executions):
        rank = 1
    else:
        rank = 2
    return rank, task.created_at, task.task_id


def dedupe_self_improvement(root: Path) -> dict:
    """Cancel duplicate source/execution tasks before GitHub Issue routing.

    Running or review work is never interrupted. Future duplicates are removed
    before the Issue router runs, so one problem produces one authoritative Issue.
    """
    root = Path(root).resolve()
    runtime = root / "runtime"
    runtime.mkdir(parents=True, exist_ok=True)
    evidence_path = runtime / "self_improvement_dedupe.json"
    queue = PersistentTaskQueue(runtime / "genesis_tasks.sqlite3")

    candidates: list[tuple[GenesisTask, list[GenesisTask]]] = []
    for task in queue.list(limit=5000):
        if not _is_source_self_improvement_task(task):
            continue
        executions = _execution_tasks(queue, task.task_id)
        if _active_source(task, executions):
            candidates.append((task, executions))

    groups: dict[str, list[tuple[GenesisTask, list[GenesisTask]]]] = {}
    for task, executions in candidates:
        groups.setdefault(problem_fingerprint(task), []).append((task, executions))

    result = {
        "status": "ok",
        "candidate_sources": len(candidates),
        "duplicate_groups": 0,
        "cancelled_sources": [],
        "cancelled_execution_tasks": [],
        "skipped_in_flight": [],
    }

    for fingerprint, rows in groups.items():
        if len(rows) < 2:
            continue
        result["duplicate_groups"] += 1
        rows.sort(key=lambda row: _canonical_rank(row[0], row[1]))
        canonical, _canonical_executions = rows[0]

        for duplicate, executions in rows[1:]:
            if duplicate.state in IN_FLIGHT_STATES or any(row.state in IN_FLIGHT_STATES for row in executions):
                result["skipped_in_flight"].append(
                    {
                        "problem_fingerprint": fingerprint,
                        "canonical_source_task_id": canonical.task_id,
                        "duplicate_source_task_id": duplicate.task_id,
                    }
                )
                continue

            reason = f"duplicate_self_improvement_problem:{fingerprint}:canonical:{canonical.task_id}"
            for execution in executions:
                if execution.state in TERMINAL_STATES:
                    continue
                cancelled = queue.cancel(execution.task_id, reason)
                result["cancelled_execution_tasks"].append(
                    {
                        "task_id": cancelled.task_id,
                        "github_issue_number": int(cancelled.payload.get("github_issue_number") or 0),
                        "canonical_source_task_id": canonical.task_id,
                    }
                )

            current = queue.get(duplicate.task_id)
            if current is not None and current.state not in TERMINAL_STATES:
                cancelled = queue.cancel(current.task_id, reason)
                result["cancelled_sources"].append(
                    {
                        "task_id": cancelled.task_id,
                        "canonical_source_task_id": canonical.task_id,
                        "problem_fingerprint": fingerprint,
                    }
                )

    if result["skipped_in_flight"]:
        result["status"] = "partial"
    evidence_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result
