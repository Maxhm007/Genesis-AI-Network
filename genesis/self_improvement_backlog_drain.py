from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

from .modules.task_queue import GenesisTask, PersistentTaskQueue
from .self_improvement_issue_router import (
    ROUTABLE_STATES,
    ROUTER_PAUSE_PREFIX,
    TERMINAL_STATES,
    _create_execution_task,
    _execution_tasks,
    _github_request,
    _is_source_self_improvement_task,
    _recoverable_paused,
    _safe_target,
    _source_marker,
)


GithubRequester = Callable[[str, str, dict | None], object | None]


def _existing_open_self_improvement_issues(requester: GithubRequester) -> list[dict]:
    rows = requester("GET", "/issues?state=open&labels=genesis-self-improvement&per_page=100", None)
    if not isinstance(rows, list):
        return []
    return [row for row in rows if isinstance(row, dict) and "pull_request" not in row]


def _matching_issue(existing: list[dict], task: GenesisTask) -> dict | None:
    marker = _source_marker(task.task_id)
    return next((row for row in existing if marker in str(row.get("body") or "")), None)


def route_existing_self_improvement(
    root: Path,
    *,
    requester: GithubRequester | None = None,
) -> dict:
    """Adopt already-open specialist Issues without publishing new work.

    This lane exists specifically for backlog-reduction mode. It never creates,
    reopens, edits, or relabels a GitHub Issue. It only converts an already-open
    authoritative self-improvement Issue into the bounded execution task expected
    by the specialist research/capability worker.
    """

    root = Path(root).resolve()
    runtime = root / "runtime"
    runtime.mkdir(parents=True, exist_ok=True)
    evidence_path = runtime / "self_improvement_backlog_drain.json"
    queue = PersistentTaskQueue(runtime / "genesis_tasks.sqlite3")
    requester = requester or _github_request
    sources = [task for task in queue.list(limit=5000) if _is_source_self_improvement_task(task)]

    result = {
        "status": "drain_existing_only",
        "source_tasks": len(sources),
        "routed": [],
        "already_routed": [],
        "deferred": [],
        "skipped_in_flight": [],
        "blocked": [],
        "policy": "adopt already-open self-improvement Issues; do not create new Issues during backlog reduction",
    }
    if not sources:
        evidence_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return result

    existing = _existing_open_self_improvement_issues(requester)
    for source in sources:
        execution = _execution_tasks(queue, source.task_id)
        if execution:
            result["already_routed"].append(
                {
                    "source_task_id": source.task_id,
                    "execution_task_id": execution[-1].task_id,
                    "github_issue_number": execution[-1].payload.get("github_issue_number"),
                    "execution_state": execution[-1].state,
                }
            )
            continue

        if source.state in {"running", "review"}:
            result["skipped_in_flight"].append(source.task_id)
            continue
        if source.state in TERMINAL_STATES:
            continue
        if source.state == "paused" and not _recoverable_paused(source):
            result["blocked"].append({"source_task_id": source.task_id, "reason": "source_task_paused_for_other_reason"})
            continue
        if source.state not in ROUTABLE_STATES and not _recoverable_paused(source):
            result["blocked"].append({"source_task_id": source.task_id, "reason": f"unsupported_source_state:{source.state}"})
            continue

        issue = _matching_issue(existing, source)
        if issue is None:
            result["deferred"].append(
                {
                    "source_task_id": source.task_id,
                    "reason": "no_existing_open_self_improvement_issue",
                }
            )
            continue

        target = _safe_target(root, source)
        if target.startswith("!"):
            result["blocked"].append({"source_task_id": source.task_id, "reason": f"invalid_target:{target}"})
            continue

        issue_number = int(issue.get("number") or 0)
        if issue_number <= 0:
            result["blocked"].append({"source_task_id": source.task_id, "reason": "invalid_existing_issue_number"})
            continue

        current = queue.get(source.task_id)
        if current is None:
            result["blocked"].append({"source_task_id": source.task_id, "reason": "source_task_disappeared"})
            continue
        if current.state in {"running", "review"}:
            result["skipped_in_flight"].append(source.task_id)
            continue
        if current.state != "paused":
            try:
                current = queue.pause(
                    source.task_id,
                    f"{ROUTER_PAUSE_PREFIX}{issue_number}: existing GitHub Issue is the exclusive self-improvement execution lane",
                )
            except Exception as exc:
                result["blocked"].append(
                    {
                        "source_task_id": source.task_id,
                        "github_issue_number": issue_number,
                        "reason": f"pause_failed:{type(exc).__name__}:{exc}",
                    }
                )
                continue

        try:
            execution_task, created = _create_execution_task(queue, current, issue, target)
        except Exception as exc:
            result["blocked"].append(
                {
                    "source_task_id": source.task_id,
                    "github_issue_number": issue_number,
                    "reason": f"execution_task_create_failed:{type(exc).__name__}:{exc}",
                }
            )
            continue

        row = {
            "source_task_id": source.task_id,
            "source_state": current.state,
            "github_issue_number": issue_number,
            "github_issue_url": str(issue.get("html_url") or ""),
            "execution_task_id": execution_task.task_id,
            "execution_state": execution_task.state,
        }
        (result["routed"] if created else result["already_routed"]).append(row)

    if result["blocked"]:
        result["status"] = "partial"
    evidence_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result
