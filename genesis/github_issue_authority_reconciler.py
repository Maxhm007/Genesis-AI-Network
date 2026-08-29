from __future__ import annotations

import json
from pathlib import Path
from typing import Callable, Iterable

from .github_issue_task_router import issue_authority_enabled
from .github_issue_terminal_reconciler import TERMINAL_STATES, _github_request, _issue_number
from .modules.task_queue import PersistentTaskQueue


GithubRequester = Callable[[str, str, dict | None], object | None]


def reconcile_closed_github_issue_tasks(
    root: Path,
    *,
    open_issue_numbers: Iterable[int],
    requester: GithubRequester | None = None,
) -> dict:
    """Make authoritative GitHub Issue closure terminal for cached task execution.

    ``open_issue_numbers`` is the current Pulse intake snapshot. A linked Issue that
    is absent from that snapshot is never assumed closed: the exact Issue is fetched
    and must explicitly report ``state=closed`` before any SQLite task row is
    cancelled. This keeps GitHub authoritative while treating SQLite as resumable
    cache state only.
    """
    root = Path(root).resolve()
    runtime = root / "runtime"
    runtime.mkdir(parents=True, exist_ok=True)
    output = runtime / "github_issue_authority_reconcile.json"
    queue = PersistentTaskQueue(runtime / "genesis_tasks.sqlite3")
    explicit_requester = requester is not None
    open_numbers = {int(number) for number in open_issue_numbers if int(number) > 0}

    groups: dict[int, list] = {}
    for task in queue.list(limit=5000):
        issue_number = _issue_number(task)
        if issue_number <= 0 or task.state in TERMINAL_STATES:
            continue
        groups.setdefault(issue_number, []).append(task)

    result = {
        "status": "ok",
        "enforced": bool(explicit_requester or issue_authority_enabled(root)),
        "open_issue_snapshot_count": len(open_numbers),
        "linked_nonterminal_issue_count": len(groups),
        "confirmed_closed": [],
        "cancelled": [],
        "skipped_open": [],
        "blocked": [],
        "policy": "A closed authoritative GitHub Issue cannot retain executable SQLite task state.",
    }

    if not result["enforced"]:
        result["status"] = "not_repository_runtime"
        output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return result

    requester = requester or _github_request
    for issue_number, tasks in sorted(groups.items()):
        if issue_number in open_numbers:
            result["skipped_open"].append(issue_number)
            continue

        issue = requester("GET", f"/issues/{issue_number}", None)
        if not isinstance(issue, dict):
            result["blocked"].append(
                {"github_issue_number": issue_number, "reason": "github_issue_unavailable_for_authority_sync"}
            )
            continue

        state = str(issue.get("state") or "").strip().lower()
        if state != "closed":
            result["skipped_open"].append(issue_number)
            continue

        state_reason = str(issue.get("state_reason") or "closed").strip() or "closed"
        result["confirmed_closed"].append(
            {"github_issue_number": issue_number, "state_reason": state_reason}
        )
        for task in tasks:
            current = queue.get(task.task_id)
            if current is None or current.state in TERMINAL_STATES:
                continue
            reason = f"authoritative GitHub Issue #{issue_number} closed ({state_reason})"
            try:
                cancelled = queue.cancel(current.task_id, reason)
            except Exception as exc:
                result["blocked"].append(
                    {
                        "github_issue_number": issue_number,
                        "task_id": current.task_id,
                        "reason": f"authority_cancel_failed:{type(exc).__name__}:{exc}",
                    }
                )
                continue
            result["cancelled"].append(
                {
                    "github_issue_number": issue_number,
                    "task_id": current.task_id,
                    "previous_state": current.state,
                    "new_state": cancelled.state,
                    "reason": reason,
                }
            )

    if result["blocked"]:
        result["status"] = "partial" if result["cancelled"] else "blocked"
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result


if __name__ == "__main__":
    raise SystemExit(
        "github_issue_authority_reconciler is invoked by Gene Pulse with its exact open-Issue snapshot"
    )
