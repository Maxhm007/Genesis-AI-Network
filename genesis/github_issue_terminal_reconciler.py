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
PROTECTED_LABELS = {"genesis-persistent", "genesis-control"}
PROTECTED_TITLE_PREFIXES = ("Genesis Control:",)

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


def reconcile_terminal_github_issues(
    root: Path,
    *,
    requester: GithubRequester | None = None,
) -> dict:
    """Close Issue-backed work only after every task linked to that Issue is terminal.

    This is deliberately conservative. Age alone is never a closure signal, persistent
    control Issues are protected, and a shared Issue remains open while any linked task
    is still new/assigned/running/review/failed/blocked. Completed work closes as
    ``completed``; an all-cancelled generation closes as ``not_planned``.
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
        "skipped_active": [],
        "skipped_protected": [],
        "blocked": [],
    }

    if not result["enforced"]:
        result["status"] = "not_repository_runtime"
        result["reason"] = "temporary/non-repository runtime; real GitHub Issue mutations are disabled"
        report_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return result

    requester = requester or _github_request

    for issue_number, tasks in sorted(groups.items()):
        active = [task for task in tasks if task.state not in TERMINAL_STATES]
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
        issue = requester("GET", f"/issues/{issue_number}", None)
        if not isinstance(issue, dict):
            result["blocked"].append(
                {"github_issue_number": issue_number, "reason": "github_issue_unavailable"}
            )
            continue

        if str(issue.get("state") or "open") == "closed":
            result["already_closed"].append(issue_number)
            continue

        if _protected_issue(issue):
            result["skipped_protected"].append(issue_number)
            continue

        state_reason = _close_reason(tasks)
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
        result["status"] = "partial" if result["closed"] or result["already_closed"] else "blocked"
    report_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    result = reconcile_terminal_github_issues(root)
    print(json.dumps(result, sort_keys=True))
    return 0 if result["status"] in {"ok", "not_repository_runtime"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
