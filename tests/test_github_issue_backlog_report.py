from __future__ import annotations

import json
from pathlib import Path

from genesis.github_issue_backlog_report import build_github_issue_backlog_report
from genesis.modules.task_queue import PersistentTaskQueue


class FakeGithub:
    def __init__(self, issues: list[dict]) -> None:
        self.issues = [dict(issue) for issue in issues]

    def __call__(self, method: str, path: str, payload: dict | None = None):
        if method == "GET" and path.startswith("/issues?state=open"):
            return [dict(issue) for issue in self.issues if str(issue.get("state") or "open") == "open"]
        return None


def _issue(number: int, *, title: str = "Task", labels: list[dict] | None = None) -> dict:
    return {
        "number": number,
        "title": title,
        "state": "open",
        "labels": labels if labels is not None else [],
    }


def _queue(root: Path) -> PersistentTaskQueue:
    return PersistentTaskQueue(root / "runtime" / "genesis_tasks.sqlite3")


def _complete(queue: PersistentTaskQueue, task_id: str) -> None:
    queue.transition(task_id, "assigned")
    queue.transition(task_id, "running")
    queue.transition(task_id, "review")
    queue.transition(task_id, "complete")


def _fail(queue: PersistentTaskQueue, task_id: str) -> None:
    queue.transition(task_id, "assigned")
    queue.record_failure(task_id, "bounded failure", retry_after_seconds=0)


def test_backlog_report_distinguishes_inventory_and_actionable_backlog(tmp_path: Path) -> None:
    github = FakeGithub([
        _issue(201, labels=[{"name": "genesis-task"}]),
        _issue(202, labels=[{"name": "genesis-action-failure"}]),
        _issue(203, title="Genesis Control: persistent", labels=[{"name": "genesis-control"}]),
        _issue(204, labels=[{"name": "genesis-task"}, {"name": "genesis-blocked"}]),
        _issue(205),
    ])

    report = build_github_issue_backlog_report(tmp_path, requester=github)

    assert report["status"] == "ok"
    assert report["raw_open_issue_count"] == 5
    assert report["actionable_backlog_count"] == 2
    assert report["actionable_backlog_issue_numbers"] == [201, 202]
    assert report["non_actionable_open_issue_count"] == 3
    assert report["actionable_task_issues"] == [201]
    assert report["action_failure_issues"] == [202]
    assert report["protected_control_persistent_issues"] == [203]
    assert report["externally_blocked_issues"] == [204]
    assert report["other_open_issues"] == [205]
    assert report["counts"] == {
        "actionable_task_issues": 1,
        "action_failure_issues": 1,
        "protected_control_persistent_issues": 1,
        "externally_blocked_issues": 1,
        "other_open_issues": 1,
    }


def test_blocked_action_failure_is_not_counted_as_actionable(tmp_path: Path) -> None:
    github = FakeGithub([
        _issue(
            210,
            labels=[
                {"name": "genesis-action-failure"},
                {"name": "genesis-action-blocked"},
                {"name": "genesis-task"},
            ],
        ),
        _issue(211, labels=[{"name": "genesis-action-failure"}]),
    ])

    report = build_github_issue_backlog_report(tmp_path, requester=github)

    assert report["externally_blocked_issues"] == [210]
    assert report["action_failure_issues"] == [211]
    assert report["actionable_task_issues"] == []
    assert report["actionable_backlog_count"] == 1
    assert report["actionable_backlog_issue_numbers"] == [211]


def test_protected_issue_precedes_blocked_or_actionable_labels(tmp_path: Path) -> None:
    github = FakeGithub([
        _issue(
            212,
            title="Genesis Control: protected repair channel",
            labels=[
                {"name": "genesis-control"},
                {"name": "genesis-blocked"},
                {"name": "genesis-task"},
            ],
        )
    ])

    report = build_github_issue_backlog_report(tmp_path, requester=github)

    assert report["protected_control_persistent_issues"] == [212]
    assert report["externally_blocked_issues"] == []
    assert report["actionable_backlog_count"] == 0


def test_backlog_report_detects_remaining_superseded_generation(tmp_path: Path) -> None:
    queue = _queue(tmp_path)
    old, _ = queue.create_unique(
        "issue-206-generation-1",
        "Old failed generation",
        payload={
            "github_issue_number": 206,
            "problem_fingerprint": "backlog:206",
            "work_generation": 1,
        },
    )
    newer, _ = queue.create_unique(
        "issue-206-generation-2",
        "Replacement generation",
        payload={
            "github_issue_number": 206,
            "problem_fingerprint": "backlog:206",
            "work_generation": 2,
        },
    )
    _fail(queue, old.task_id)
    _complete(queue, newer.task_id)
    github = FakeGithub([_issue(206, labels=[{"name": "genesis-task"}])])

    report = build_github_issue_backlog_report(tmp_path, requester=github)

    stale = report["stale_or_superseded_generations"]
    assert stale["remaining_detected_count"] == 1
    assert stale["remaining_detected"][0]["task_id"] == old.task_id
    assert stale["remaining_detected"][0]["github_issue_number"] == 206


def test_backlog_report_carries_retired_supersession_evidence(tmp_path: Path) -> None:
    runtime = tmp_path / "runtime"
    runtime.mkdir(parents=True, exist_ok=True)
    retired = {
        "github_issue_number": 207,
        "task_id": "task-old",
        "previous_state": "failed",
        "new_state": "cancelled",
        "reason": "superseded by generation 2",
    }
    (runtime / "github_issue_terminal_reconcile.json").write_text(
        json.dumps({"superseded": [retired]}) + "\n",
        encoding="utf-8",
    )
    github = FakeGithub([_issue(207, labels=[{"name": "genesis-task"}])])

    report = build_github_issue_backlog_report(tmp_path, requester=github)

    stale = report["stale_or_superseded_generations"]
    assert stale["remaining_detected_count"] == 0
    assert stale["retired_this_reconcile_count"] == 1
    assert stale["retired_this_reconcile"] == [retired]
