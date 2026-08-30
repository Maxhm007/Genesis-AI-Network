from __future__ import annotations

import json
import os
from pathlib import Path
import urllib.error
import urllib.request
from typing import Callable

from .github_issue_task_router import issue_authority_enabled
from .modules.task_queue import GenesisTask, PersistentTaskQueue


TERMINAL_STATES = {"complete", "cancelled"}
GENERATION_SUPERSEDEABLE_STATES = {"failed", "blocked", "quarantined"}
EXPLICIT_SUPERSEDEABLE_STATES = {"new", "assigned", "paused", "blocked", "failed", "quarantined"}
PROTECTED_LABELS = {"genesis-persistent", "genesis-control"}
PROTECTED_TITLE_PREFIXES = ("Genesis Control:",)
SPECIALIST_HANDOFF_REASONS = {"issue_route_migrated_to_self_improvement_specialist"}
SPECIALIST_TASK_TYPES = {
    "competitive_ai_improvement",
    "competitive_reference_refresh",
    "immortality_research",
}
LINEAGE_KEYS = (
    "problem_fingerprint",
    "issue_key",
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
            "User-Agent": "Genesis-AI-Network/github-issue-terminal-reconciler",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = response.read().decode("utf-8")
        return json.loads(raw) if raw.strip() else {}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        print(f"GitHub terminal reconciler HTTP {exc.code}: {detail}")
        return None
    except Exception as exc:
        print(f"GitHub terminal reconciler unavailable: {type(exc).__name__}: {exc}")
        return None


def _issue_number(task: GenesisTask) -> int:
    try:
        return int(task.payload.get("github_issue_number") or 0)
    except (TypeError, ValueError):
        return 0


def _issue_labels(issue: dict) -> set[str]:
    result: set[str] = set()
    for label in issue.get("labels") or []:
        if isinstance(label, dict):
            name = str(label.get("name") or "").strip()
        else:
            name = str(label or "").strip()
        if name:
            result.add(name)
    return result


def _protected_issue(issue: dict) -> bool:
    title = str(issue.get("title") or "").strip()
    if any(title.startswith(prefix) for prefix in PROTECTED_TITLE_PREFIXES):
        return True
    return bool(_issue_labels(issue) & PROTECTED_LABELS)


def _close_reason(tasks: list[GenesisTask]) -> str:
    return "completed" if any(task.state == "complete" for task in tasks) else "not_planned"


def _is_specialist_handoff(task: GenesisTask) -> bool:
    """Return whether cancellation transfers Issue authority rather than ending work."""
    if task.state != "cancelled":
        return False
    return str(task.state_reason or "").strip() in SPECIALIST_HANDOFF_REASONS


def _is_specialist_replacement(task: GenesisTask) -> bool:
    """Return whether this row is real work owned by the specialist lane."""
    return str(task.payload.get("task_type") or "").strip() in SPECIALIST_TASK_TYPES


def _work_generation(task: GenesisTask) -> int:
    try:
        return max(0, int(task.payload.get("work_generation") or 0))
    except (TypeError, ValueError):
        return 0


def _lineage_key(task: GenesisTask) -> tuple[str, str] | None:
    """Return explicit lineage evidence for generation-based supersession."""
    payload = dict(task.payload or {})
    for key in LINEAGE_KEYS:
        value = str(payload.get(key) or "").strip()
        if value:
            return key, value
    return None


def _task_ids(value: object) -> set[str]:
    if isinstance(value, str):
        return {value.strip()} if value.strip() else set()
    if isinstance(value, (list, tuple, set)):
        return {str(item).strip() for item in value if str(item).strip()}
    return set()


def _supersession_reasons(tasks: list[GenesisTask]) -> dict[str, str]:
    """Identify obsolete task rows only from auditable supersession evidence.

    Explicit task-id links may retire queued/paused/failed historical work, but never
    interrupt a running or review task. Generation-based supersession is narrower:
    it requires a shared explicit lineage key plus a higher ``work_generation`` and
    only retires older failed/blocked/quarantined generations. Merely being newer is
    never enough.
    """
    by_id = {task.task_id: task for task in tasks}
    reasons: dict[str, str] = {}

    for task in tasks:
        payload = dict(task.payload or {})
        supersedes = _task_ids(payload.get("supersedes_task_id")) | _task_ids(payload.get("supersedes_task_ids"))
        for old_id in sorted(supersedes):
            old = by_id.get(old_id)
            if old is None or old.state not in EXPLICIT_SUPERSEDEABLE_STATES:
                continue
            reasons[old_id] = f"explicitly superseded by {task.task_id}"

        superseded_by = _task_ids(payload.get("superseded_by_task_id")) | _task_ids(payload.get("superseded_by_task_ids"))
        replacements = sorted(task_id for task_id in superseded_by if task_id in by_id)
        if replacements and task.state in EXPLICIT_SUPERSEDEABLE_STATES:
            reasons[task.task_id] = f"explicitly superseded by {', '.join(replacements)}"

    lineages: dict[tuple[str, str], list[GenesisTask]] = {}
    for task in tasks:
        generation = _work_generation(task)
        lineage = _lineage_key(task)
        if generation > 0 and lineage is not None:
            lineages.setdefault(lineage, []).append(task)

    for lineage, rows in lineages.items():
        highest = max(_work_generation(task) for task in rows)
        if highest <= 1:
            continue
        current_ids = sorted(task.task_id for task in rows if _work_generation(task) == highest)
        for task in rows:
            generation = _work_generation(task)
            if generation >= highest or task.state not in GENERATION_SUPERSEDEABLE_STATES:
                continue
            reasons.setdefault(
                task.task_id,
                (
                    f"superseded within {lineage[0]}={lineage[1]} by work_generation "
                    f"{highest} ({', '.join(current_ids)})"
                ),
            )

    return reasons


def reconcile_terminal_github_issues(
    root: Path,
    *,
    requester: GithubRequester | None = None,
) -> dict:
    """Close Issue-backed work after authoritative linked generations are terminal.

    Historical rows are never ignored merely because they are old. A non-terminal
    row stops closure unless auditable supersession evidence explicitly retires it.
    Protected/control Issues remain untouched, and running/review work is never
    auto-cancelled by reconciliation. A cancelled row that explicitly hands Issue
    authority to a specialist lane is not a final disposition by itself; the Issue
    stays open until a real supported specialist replacement row is linked.
    """
    root = Path(root).resolve()
    runtime = root / "runtime"
    runtime.mkdir(parents=True, exist_ok=True)
    report_path = runtime / "github_issue_terminal_reconcile.json"
    queue = PersistentTaskQueue(runtime / "genesis_tasks.sqlite3")
    explicit_requester = requester is not None

    groups: dict[int, list[GenesisTask]] = {}
    for task in queue.list(limit=5000):
        issue_number = _issue_number(task)
        if issue_number > 0:
            groups.setdefault(issue_number, []).append(task)

    result = {
        "status": "ok",
        "enforced": bool(explicit_requester or issue_authority_enabled(root)),
        "linked_issue_count": len(groups),
        "eligible": [],
        "closed": [],
        "already_closed": [],
        "superseded": [],
        "skipped_active": [],
        "skipped_handoff": [],
        "skipped_protected": [],
        "blocked": [],
    }

    if not result["enforced"]:
        result["status"] = "not_repository_runtime"
        result["reason"] = "temporary/non-repository runtime; real GitHub Issue mutations are disabled"
        report_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return result

    requester = requester or _github_request

    for issue_number, original_tasks in sorted(groups.items()):
        tasks = list(original_tasks)
        supersession = _supersession_reasons(tasks)
        issue: dict | None = None

        if supersession:
            fetched = requester("GET", f"/issues/{issue_number}", None)
            if not isinstance(fetched, dict):
                result["blocked"].append(
                    {"github_issue_number": issue_number, "reason": "github_issue_unavailable_for_supersession"}
                )
                continue
            issue = fetched
            if str(issue.get("state") or "open") == "closed":
                result["already_closed"].append(issue_number)
                continue
            if _protected_issue(issue):
                result["skipped_protected"].append(issue_number)
                continue

            for task_id, reason in sorted(supersession.items()):
                current = queue.get(task_id)
                if current is None or current.state in TERMINAL_STATES:
                    continue
                try:
                    cancelled = queue.cancel(task_id, reason)
                except Exception as exc:
                    result["blocked"].append(
                        {
                            "github_issue_number": issue_number,
                            "task_id": task_id,
                            "reason": f"supersession_cancel_failed:{type(exc).__name__}:{exc}",
                        }
                    )
                    continue
                result["superseded"].append(
                    {
                        "github_issue_number": issue_number,
                        "task_id": task_id,
                        "previous_state": current.state,
                        "new_state": cancelled.state,
                        "reason": reason,
                    }
                )
            tasks = [queue.get(task.task_id) or task for task in tasks]

        handoff_tasks = [task for task in tasks if _is_specialist_handoff(task)]
        substantive_tasks = [task for task in tasks if not _is_specialist_handoff(task)]
        specialist_replacements = [task for task in substantive_tasks if _is_specialist_replacement(task)]
        if handoff_tasks and not specialist_replacements:
            result["skipped_handoff"].append(
                {
                    "github_issue_number": issue_number,
                    "handoff_task_ids": [task.task_id for task in handoff_tasks],
                    "reason": "awaiting_specialist_replacement",
                }
            )
            continue

        active = [task for task in substantive_tasks if task.state not in TERMINAL_STATES]
        if active:
            result["skipped_active"].append(
                {
                    "github_issue_number": issue_number,
                    "active_task_ids": [task.task_id for task in active],
                    "states": sorted({task.state for task in active}),
                }
            )
            continue

        result["eligible"].append(issue_number)
        if issue is None:
            fetched = requester("GET", f"/issues/{issue_number}", None)
            if not isinstance(fetched, dict):
                result["blocked"].append(
                    {"github_issue_number": issue_number, "reason": "github_issue_unavailable"}
                )
                continue
            issue = fetched

        if str(issue.get("state") or "open") == "closed":
            result["already_closed"].append(issue_number)
            continue

        if _protected_issue(issue):
            result["skipped_protected"].append(issue_number)
            continue

        state_reason = _close_reason(substantive_tasks)
        updated = requester(
            "PATCH",
            f"/issues/{issue_number}",
            {"state": "closed", "state_reason": state_reason},
        )
        if isinstance(updated, dict) and str(updated.get("state") or "") == "closed":
            result["closed"].append(
                {
                    "github_issue_number": issue_number,
                    "state_reason": state_reason,
                    "task_ids": [task.task_id for task in tasks],
                }
            )
        else:
            result["blocked"].append(
                {"github_issue_number": issue_number, "reason": "github_close_failed"}
            )

    if result["blocked"]:
        result["status"] = "partial" if result["closed"] or result["already_closed"] or result["superseded"] else "blocked"
    report_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    result = reconcile_terminal_github_issues(root)
    print(json.dumps(result, sort_keys=True))
    return 0 if result["status"] in {"ok", "not_repository_runtime"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
