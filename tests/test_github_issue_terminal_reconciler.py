from __future__ import annotations

from pathlib import Path

from genesis.github_issue_terminal_reconciler import reconcile_terminal_github_issues
from genesis.modules.task_queue import PersistentTaskQueue


class FakeGithub:
    def __init__(self, issues: list[dict]) -> None:
        self.issues = {int(issue["number"]): dict(issue) for issue in issues}
        self.calls: list[tuple[str, str, dict | None]] = []

    def __call__(self, method: str, path: str, payload: dict | None = None):
        self.calls.append((method, path, payload))
        if path.startswith("/issues/"):
            number = int(path.rsplit("/", 1)[1])
            issue = self.issues.get(number)
            if issue is None:
                return None
            if method == "GET":
                return dict(issue)
            if method == "PATCH":
                issue.update(payload or {})
                return dict(issue)
        return None


def _queue(root: Path) -> PersistentTaskQueue:
    return PersistentTaskQueue(root / "runtime" / "genesis_tasks.sqlite3")


def _complete(queue: PersistentTaskQueue, task_id: str) -> None:
    queue.transition(task_id, "assigned")
    queue.transition(task_id, "running")
    queue.transition(task_id, "review")
    queue.transition(task_id, "complete")


def test_completed_issue_backed_task_closes_issue(tmp_path: Path) -> None:
    queue = _queue(tmp_path)
    task, _ = queue.create_unique(
        "terminal-close",
        "Repair the issue and close it after verified completion",
        payload={"task_type": "github_issue_development", "github_issue_number": 42},
    )
    _complete(queue, task.task_id)
    github = FakeGithub([
        {"number": 42, "title": "Repair defect", "state": "open", "labels": [{"name": "genesis-task"}]}
    ])

    result = reconcile_terminal_github_issues(tmp_path, requester=github)

    assert result["status"] == "ok"
    assert result["closed"] == [
        {"github_issue_number": 42, "state_reason": "completed", "task_ids": [task.task_id]}
    ]
    assert github.issues[42]["state"] == "closed"
    assert github.issues[42]["state_reason"] == "completed"


def test_shared_issue_stays_open_while_any_linked_task_is_active(tmp_path: Path) -> None:
    queue = _queue(tmp_path)
    finished, _ = queue.create_unique(
        "shared-finished",
        "Finished generation",
        payload={"github_issue_number": 77},
    )
    active, _ = queue.create_unique(
        "shared-active",
        "Still active generation",
        payload={"github_issue_number": 77},
    )
    _complete(queue, finished.task_id)
    queue.transition(active.task_id, "assigned")
    github = FakeGithub([
        {"number": 77, "title": "Shared task", "state": "open", "labels": [{"name": "genesis-task"}]}
    ])

    result = reconcile_terminal_github_issues(tmp_path, requester=github)

    assert result["closed"] == []
    assert result["skipped_active"][0]["github_issue_number"] == 77
    assert result["skipped_active"][0]["active_task_ids"] == [active.task_id]
    assert github.issues[77]["state"] == "open"
    assert not any(method == "PATCH" for method, _, _ in github.calls)


def test_cancelled_task_closes_as_not_planned(tmp_path: Path) -> None:
    queue = _queue(tmp_path)
    task, _ = queue.create_unique(
        "terminal-cancel",
        "Superseded task generation",
        payload={"github_issue_number": 88},
    )
    queue.cancel(task.task_id, "superseded by a newer task generation")
    github = FakeGithub([
        {"number": 88, "title": "Superseded task", "state": "open", "labels": [{"name": "genesis-task"}]}
    ])

    result = reconcile_terminal_github_issues(tmp_path, requester=github)

    assert result["closed"][0]["state_reason"] == "not_planned"
    assert github.issues[88]["state_reason"] == "not_planned"


def test_persistent_control_issue_is_never_auto_closed(tmp_path: Path) -> None:
    queue = _queue(tmp_path)
    task, _ = queue.create_unique(
        "persistent-control",
        "Persistent control task",
        payload={"github_issue_number": 4},
    )
    _complete(queue, task.task_id)
    github = FakeGithub([
        {
            "number": 4,
            "title": "Genesis Control: hourly autonomous report",
            "state": "open",
            "labels": [{"name": "genesis-persistent"}],
        }
    ])

    result = reconcile_terminal_github_issues(tmp_path, requester=github)

    assert result["skipped_protected"] == [4]
    assert result["closed"] == []
    assert github.issues[4]["state"] == "open"
