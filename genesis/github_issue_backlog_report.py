from __future__ import annotations

import json
import os
from pathlib import Path
import urllib.error
import urllib.request
from typing import Callable

from .github_issue_terminal_reconciler import _issue_number, _supersession_reasons
from .modules.task_queue import PersistentTaskQueue


PROTECTED_LABELS = {"genesis-persistent", "genesis-control"}
PROTECTED_TITLE_PREFIXES = ("Genesis Control:",)
ACTION_FAILURE_LABEL = "genesis-action-failure"
EXTERNAL_BLOCK_LABELS = {"genesis-blocked", "genesis-action-blocked"}
ACTIONABLE_LABELS = {"genesis-task", "genesis-autonomous", "genesis-self-improvement"}

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
            "User-Agent": "Genesis-AI-Network/github-issue-backlog-report",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = response.read().decode("utf-8")
        return json.loads(raw) if raw.strip() else {}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        print(f"GitHub backlog report HTTP {exc.code}: {detail}")
        return None
    except Exception as exc:
        print(f"GitHub backlog report unavailable: {type(exc).__name__}: {exc}")
        return None


def _labels(issue: dict) -> set[str]:
    result: set[str] = set()
    for label in issue.get("labels") or []:
        name = str(label.get("name") if isinstance(label, dict) else label or "").strip()
        if name:
            result.add(name)
    return result


def _protected(issue: dict) -> bool:
    title = str(issue.get("title") or "").strip()
    return any(title.startswith(prefix) for prefix in PROTECTED_TITLE_PREFIXES) or bool(
        _labels(issue) & PROTECTED_LABELS
    )


def _open_issues(requester: GithubRequester, *, max_pages: int = 10) -> list[dict] | None:
    result: list[dict] = []
    for page in range(1, max_pages + 1):
        rows = requester("GET", f"/issues?state=open&per_page=100&page={page}", None)
        if not isinstance(rows, list):
            return None
        result.extend(row for row in rows if isinstance(row, dict) and "pull_request" not in row)
        if len(rows) < 100:
            break
    return result


def _classify(issues: list[dict]) -> dict[str, list[int]]:
    """Classify open Issue inventory with non-actionable states taking precedence."""
    categories: dict[str, list[int]] = {
        "actionable_task_issues": [],
        "action_failure_issues": [],
        "protected_control_persistent_issues": [],
        "externally_blocked_issues": [],
        "other_open_issues": [],
    }
    for issue in sorted(issues, key=lambda row: int(row.get("number") or 0)):
        number = int(issue.get("number") or 0)
        if number <= 0:
            continue
        labels = _labels(issue)

        # Non-actionable classifications win even when an Issue also carries an
        # actionable/task/failure label. This prevents blocked Action failures from
        # being reported as work Genesis can currently execute.
        if _protected(issue):
            categories["protected_control_persistent_issues"].append(number)
        elif labels & EXTERNAL_BLOCK_LABELS:
            categories["externally_blocked_issues"].append(number)
        elif ACTION_FAILURE_LABEL in labels:
            categories["action_failure_issues"].append(number)
        elif labels & ACTIONABLE_LABELS:
            categories["actionable_task_issues"].append(number)
        else:
            categories["other_open_issues"].append(number)
    return categories


def _remaining_supersession_candidates(queue: PersistentTaskQueue) -> list[dict]:
    groups: dict[int, list] = {}
    for task in queue.list(limit=5000):
        issue_number = _issue_number(task)
        if issue_number > 0:
            groups.setdefault(issue_number, []).append(task)

    result: list[dict] = []
    for issue_number, tasks in sorted(groups.items()):
        by_id = {task.task_id: task for task in tasks}
        for task_id, reason in sorted(_supersession_reasons(tasks).items()):
            task = by_id.get(task_id)
            result.append(
                {
                    "github_issue_number": issue_number,
                    "task_id": task_id,
                    "state": task.state if task is not None else "unknown",
                    "reason": reason,
                }
            )
    return result


def build_github_issue_backlog_report(
    root: Path,
    *,
    requester: GithubRequester | None = None,
) -> dict:
    root = Path(root).resolve()
    runtime = root / "runtime"
    runtime.mkdir(parents=True, exist_ok=True)
    output = runtime / "github_issue_backlog_report.json"
    queue = PersistentTaskQueue(runtime / "genesis_tasks.sqlite3")
    requester = requester or _github_request

    issues = _open_issues(requester)
    if issues is None:
        report = {
            "status": "unavailable",
            "policy": "raw open Issue count is inventory, not actionable backlog",
            "reason": "github_open_issue_snapshot_unavailable",
        }
        output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return report

    categories = _classify(issues)
    actionable_issue_numbers = sorted(
        categories["actionable_task_issues"] + categories["action_failure_issues"]
    )
    terminal_report_path = runtime / "github_issue_terminal_reconcile.json"
    terminal_report: dict = {}
    if terminal_report_path.is_file():
        try:
            loaded = json.loads(terminal_report_path.read_text(encoding="utf-8"))
            terminal_report = loaded if isinstance(loaded, dict) else {}
        except (OSError, json.JSONDecodeError):
            terminal_report = {}

    remaining = _remaining_supersession_candidates(queue)
    retired = list(terminal_report.get("superseded") or [])
    raw_open_count = len(issues)
    report = {
        "status": "ok",
        "policy": "raw open Issue count is inventory, not actionable backlog",
        "raw_open_issue_count": raw_open_count,
        "actionable_backlog_count": len(actionable_issue_numbers),
        "actionable_backlog_issue_numbers": actionable_issue_numbers,
        "non_actionable_open_issue_count": raw_open_count - len(actionable_issue_numbers),
        "counts": {name: len(numbers) for name, numbers in categories.items()},
        **categories,
        "stale_or_superseded_generations": {
            "remaining_detected_count": len(remaining),
            "remaining_detected": remaining,
            "retired_this_reconcile_count": len(retired),
            "retired_this_reconcile": retired,
        },
    }
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    report = build_github_issue_backlog_report(root)
    print(json.dumps(report, sort_keys=True))
    return 0 if report["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
