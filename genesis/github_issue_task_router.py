from __future__ import annotations

import json
import os
from pathlib import Path
import sqlite3
import urllib.error
import urllib.request
from typing import Callable

from .issue_backpressure import active_capacity_count, capacity_limited_task, configured_max_active
from .issue_fingerprint import canonical_issue_fingerprint, canonical_task_fingerprint
from .modules.task_queue import GenesisTask, PersistentTaskQueue, utc_now


GENESIS_TASK_LABEL = "genesis-task"
AUTONOMOUS_REPAIR_LABEL = "genesis-autonomous"
TITLE_PREFIX = "[Genesis Task]"
SOURCE_MARKER_PREFIX = "<!-- genesis-task-id:"
CAPABILITY_SOURCE_PREFIX = "<!-- genesis-capability-source:"
SELF_IMPROVEMENT_SOURCE_PREFIX = "<!-- genesis-self-improvement-source:"
TERMINAL_STATES = {"complete", "cancelled"}
LINK_KEYS = (
    "source_self_improvement_task_id",
    "source_capability_task_id",
    "source_task_id",
)

GithubRequester = Callable[[str, str, dict | None], object | None]


def _github_request(method: str, path: str, payload: dict | None = None):
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    repo = os.environ.get("GITHUB_REPOSITORY", "").strip()
    if not token or not repo:
        return None
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        f"https://api.github.com/repos/{repo}{path}",
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "Content-Type": "application/json",
            "User-Agent": "Genesis-AI-Network/github-issue-task-router",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = response.read().decode("utf-8")
        return json.loads(raw) if raw.strip() else {}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        print(f"GitHub task router HTTP {exc.code}: {detail}")
        return None
    except Exception as exc:
        print(f"GitHub task router unavailable: {type(exc).__name__}: {exc}")
        return None


def issue_authority_enabled(root: Path) -> bool:
    """Return whether this path is the real Genesis repository runtime.

    Unit tests frequently create temporary SQLite queues while GitHub Actions still
    exposes repository credentials. Those fixtures must never create real Issues.
    The actual Actions checkout is identified by GITHUB_WORKSPACE; local production
    clones are identified by their .git directory. Tests can explicitly force this
    policy with GENESIS_FORCE_GITHUB_TASK_AUTHORITY=1 or an injected requester.
    """
    root = Path(root).resolve()
    if os.environ.get("GENESIS_FORCE_GITHUB_TASK_AUTHORITY", "").strip() == "1":
        return True
    workspace = os.environ.get("GITHUB_WORKSPACE", "").strip()
    if workspace:
        try:
            return root == Path(workspace).resolve()
        except OSError:
            return False
    return (root / ".git").exists()


def issue_backed(task: GenesisTask) -> bool:
    return int(task.payload.get("github_issue_number") or 0) > 0


def _source_marker(task_id: str) -> str:
    return f"{SOURCE_MARKER_PREFIX}{task_id} -->"


def _legacy_markers(task_id: str) -> tuple[str, str]:
    return (
        f"{CAPABILITY_SOURCE_PREFIX}{task_id} -->",
        f"{SELF_IMPROVEMENT_SOURCE_PREFIX}{task_id} -->",
    )


def _problem_fingerprint(task: GenesisTask) -> str:
    existing = str(task.payload.get("problem_fingerprint") or "").strip()
    if existing and not existing.startswith("genesis-task:"):
        return existing
    return canonical_task_fingerprint(task)


def _task_type(task: GenesisTask) -> str:
    return str(task.payload.get("task_type") or "autonomous_task").strip() or "autonomous_task"


def _issue_title(task: GenesisTask) -> str:
    objective = " ".join(str(task.objective or "").split())
    task_type = _task_type(task).replace("_", " ")
    return f"{TITLE_PREFIX} {task_type} — {(objective or task.task_id)[:150]}"[:240]


def _issue_body(task: GenesisTask) -> str:
    payload = dict(task.payload or {})
    acceptance = str(payload.get("acceptance") or payload.get("required_outcome") or "").strip()
    if not acceptance:
        acceptance = (
            "Complete the stated objective with verifiable evidence while preserving tests, Security, "
            "independent validation, protected-file boundaries, signing boundaries, secret boundaries, "
            "owner control, and exact promotion requirements where code changes are involved."
        )
    target = str(payload.get("target_path") or "").strip()
    source = str(payload.get("source") or "genesis").strip()
    target_line = f"- **Target:** `{target}`\n" if target else ""
    return (
        f"{_source_marker(task.task_id)}\n"
        "This GitHub Issue is the authoritative task record for this Genesis autonomous work item. "
        "SQLite/runtime state may cache execution progress, but it is not an independent task source.\n\n"
        f"Genesis-Problem-Fingerprint: {_problem_fingerprint(task)}\n"
        f"- **Genesis task ID:** `{task.task_id}`\n"
        f"- **Task type:** `{_task_type(task)}`\n"
        f"- **Source:** `{source}`\n"
        f"- **Owning module:** `{task.module_id or 'unassigned'}`\n"
        f"- **Priority:** {task.priority}\n"
        f"{target_line}\n"
        "### Objective\n"
        f"{str(task.objective)[:10000]}\n\n"
        "### Acceptance\n"
        f"{acceptance[:6000]}\n\n"
        "### Authority rule\n"
        "- Genesis must not execute this work unless it is linked to this or another explicit GitHub Issue.\n"
        "- User-created actionable Issues enter the same autonomous intake and execution pipeline.\n"
        "- Failure/review/validation evidence stays attached to the Issue-backed task generation.\n"
        "- Code changes still require tests, Security review, independent validation, and promotion controls.\n"
    )


def _ensure_label(requester: GithubRequester) -> bool:
    labels = requester("GET", "/labels?per_page=100", None)
    if not isinstance(labels, list):
        return False
    if any(isinstance(row, dict) and row.get("name") == GENESIS_TASK_LABEL for row in labels):
        return True
    created = requester(
        "POST",
        "/labels",
        {
            "name": GENESIS_TASK_LABEL,
            "color": "0e8a16",
            "description": "Authoritative GitHub Issue backing for Genesis autonomous tasks",
        },
    )
    return isinstance(created, dict) and created.get("name") == GENESIS_TASK_LABEL


def _all_issues(requester: GithubRequester, *, max_pages: int = 10) -> list[dict]:
    result: list[dict] = []
    for page in range(1, max_pages + 1):
        rows = requester("GET", f"/issues?state=all&per_page=100&page={page}", None)
        if not isinstance(rows, list):
            return result
        issue_rows = [row for row in rows if isinstance(row, dict) and "pull_request" not in row]
        result.extend(issue_rows)
        if len(rows) < 100:
            break
    return result


def _find_issue_for_task(existing: list[dict], task: GenesisTask) -> dict | None:
    markers = (_source_marker(task.task_id), *_legacy_markers(task.task_id))
    fingerprint = _problem_fingerprint(task)
    fingerprint_line = f"Genesis-Problem-Fingerprint: {fingerprint}"
    for issue in existing:
        body = str(issue.get("body") or "")
        if any(marker in body for marker in markers):
            return issue
        if fingerprint_line in body:
            return issue
        if canonical_issue_fingerprint(body) == fingerprint:
            return issue
    return None


def _linked_issue_from_queue(queue: PersistentTaskQueue, source_task_id: str) -> tuple[int, str] | None:
    for candidate in queue.list(limit=5000):
        if not issue_backed(candidate):
            continue
        payload = dict(candidate.payload or {})
        if any(str(payload.get(key) or "") == source_task_id for key in LINK_KEYS):
            return (
                int(payload.get("github_issue_number") or 0),
                str(payload.get("github_issue_url") or ""),
            )
    return None


def _bind_issue(queue: PersistentTaskQueue, task: GenesisTask, issue_number: int, issue_url: str) -> GenesisTask:
    payload = dict(task.payload or {})
    payload.update(
        {
            "github_issue_number": int(issue_number),
            "github_issue_url": str(issue_url or ""),
            "execution_lane": "github_issue",
            "github_issue_authoritative": True,
            "problem_fingerprint": _problem_fingerprint(task),
        }
    )
    with sqlite3.connect(queue.path) as db:
        db.execute(
            "UPDATE genesis_tasks SET payload_json = ?, updated_at = ? WHERE task_id = ?",
            (json.dumps(payload, sort_keys=True), utc_now(), task.task_id),
        )
    updated = queue.get(task.task_id)
    if updated is None:
        raise KeyError(task.task_id)
    return updated


def _ensure_issue(
    requester: GithubRequester,
    existing: list[dict],
    task: GenesisTask,
) -> dict | None:
    issue = _find_issue_for_task(existing, task)
    title = _issue_title(task)
    body = _issue_body(task)
    if issue is None:
        created = requester(
            "POST",
            "/issues",
            {"title": title, "body": body, "labels": [GENESIS_TASK_LABEL, AUTONOMOUS_REPAIR_LABEL]},
        )
        if isinstance(created, dict) and int(created.get("number") or 0) > 0:
            existing.append(created)
            return created
        return None

    # Preserve richer specialist issue text/labels if one already owns the task.
    body_text = str(issue.get("body") or "")
    is_general = _source_marker(task.task_id) in body_text
    patch: dict[str, object] = {}
    if is_general and str(issue.get("title") or "") != title:
        patch["title"] = title
    if is_general and body_text != body:
        patch["body"] = body
    if str(issue.get("state") or "open") != "open" and task.state not in TERMINAL_STATES:
        patch["state"] = "open"
    if patch:
        updated = requester("PATCH", f"/issues/{int(issue['number'])}", patch)
        if isinstance(updated, dict):
            issue = updated
    return issue


def route_unbacked_tasks(
    root: Path,
    *,
    requester: GithubRequester | None = None,
) -> dict:
    """Bind non-terminal autonomous tasks to GitHub Issues before execution.

    GitHub Issues are authoritative. The SQLite queue is execution/cache state only.
    Existing matching Issues are always reused before admission capacity is tested.
    Low-priority research/capability candidates are left unbacked and therefore
    non-executable when the active autonomous backlog is full; they remain durable
    in the same queue and are reconsidered on the next routing cycle. Repair,
    security/action-failure and owner-prioritized work bypasses that admission cap.

    An injected requester explicitly opts a caller (normally a unit test) into the
    real routing behavior without requiring the caller to be the production repo.
    """
    root = Path(root).resolve()
    runtime = root / "runtime"
    runtime.mkdir(parents=True, exist_ok=True)
    report_path = runtime / "github_issue_task_router.json"
    queue = PersistentTaskQueue(runtime / "genesis_tasks.sqlite3")
    explicit_requester = requester is not None

    candidates = [
        task
        for task in queue.list(limit=5000)
        if task.state not in TERMINAL_STATES and not issue_backed(task)
    ]
    max_active = configured_max_active()
    result = {
        "status": "ok",
        "enforced": bool(explicit_requester or issue_authority_enabled(root)),
        "policy": "GitHub Issues are the authoritative task source; SQLite is execution/cache state only.",
        "candidate_count": len(candidates),
        "backpressure": {
            "max_active_autonomous_issues": max_active,
            "active_capacity_issues": 0,
        },
        "bound": [],
        "adopted": [],
        "deferred": [],
        "blocked": [],
    }

    if not result["enforced"]:
        result["status"] = "not_repository_runtime"
        result["reason"] = "temporary/non-repository runtime; real GitHub Issue mutations are disabled"
        report_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return result

    if not candidates:
        report_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return result

    requester = requester or _github_request
    if not _ensure_label(requester):
        result["status"] = "blocked"
        result["reason"] = "GitHub Issue lane unavailable; unbacked tasks remain non-executable"
        result["blocked"] = [task.task_id for task in candidates]
        report_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return result

    existing = _all_issues(requester)
    active_limited = active_capacity_count(existing)
    result["backpressure"]["active_capacity_issues"] = active_limited

    for task in candidates:
        linked = _linked_issue_from_queue(queue, task.task_id)
        if linked is not None:
            issue_number, issue_url = linked
            updated = _bind_issue(queue, task, issue_number, issue_url)
            result["adopted"].append(
                {
                    "task_id": updated.task_id,
                    "github_issue_number": issue_number,
                    "github_issue_url": issue_url,
                    "reason": "reused_issue_from_linked_execution_task",
                }
            )
            continue

        # Dedupe/reuse happens before capacity admission. Existing authoritative
        # work must never receive a second issue merely because the backlog is full.
        matched = _find_issue_for_task(existing, task)
        if matched is not None:
            was_open = str(matched.get("state") or "open") == "open"
            issue = _ensure_issue(requester, existing, task)
            if issue is None:
                result["blocked"].append({"task_id": task.task_id, "reason": "github_issue_unavailable"})
                continue
            if capacity_limited_task(task) and not was_open and str(issue.get("state") or "open") == "open":
                active_limited += 1
            issue_number = int(issue.get("number") or 0)
            issue_url = str(issue.get("html_url") or "")
            updated = _bind_issue(queue, task, issue_number, issue_url)
            result["adopted"].append(
                {
                    "task_id": updated.task_id,
                    "github_issue_number": issue_number,
                    "github_issue_url": issue_url,
                    "reason": "reused_existing_canonical_issue",
                }
            )
            continue

        limited = capacity_limited_task(task)
        if limited and active_limited >= max_active:
            result["deferred"].append(
                {
                    "task_id": task.task_id,
                    "task_type": _task_type(task),
                    "priority": task.priority,
                    "created_at": task.created_at,
                    "reason": "active_autonomous_backlog_at_capacity",
                }
            )
            continue

        issue = _ensure_issue(requester, existing, task)
        if issue is None:
            result["blocked"].append({"task_id": task.task_id, "reason": "github_issue_unavailable"})
            continue

        if limited:
            active_limited += 1
        issue_number = int(issue.get("number") or 0)
        issue_url = str(issue.get("html_url") or "")
        updated = _bind_issue(queue, task, issue_number, issue_url)
        result["bound"].append(
            {
                "task_id": updated.task_id,
                "github_issue_number": issue_number,
                "github_issue_url": issue_url,
            }
        )

    result["backpressure"]["active_capacity_issues_after_routing"] = active_limited
    if result["blocked"]:
        result["status"] = "partial" if result["bound"] or result["adopted"] else "blocked"
    report_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result
