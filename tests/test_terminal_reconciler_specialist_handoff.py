from __future__ import annotations

from pathlib import Path

from genesis.github_issue_terminal_reconciler import reconcile_terminal_github_issues
from genesis.modules.task_queue import PersistentTaskQueue


HANDOFF_REASON = "issue_route_migrated_to_self_improvement_specialist"


class FakeGithub:
    def __init__(self, issue_number: int) -> None:
        self.issue = {
            "number": issue_number,
            "title": "[Genesis Self Improvement] specialist work",
            "state": "open",
            "labels": [{"name": "genesis-self-improvement"}, {"name": "genesis-task"}],
        }
        self.calls: list[tuple[str, str, dict | None]] = []

    def __call__(self, method: str, path: str, payload: dict | None = None):
        self.calls.append((method, path, payload))
        if method == "GET":
            return dict(self.issue)
        if method == "PATCH":
            self.issue.update(payload or {})
            return dict(self.issue)
        return None


def _queue(root: Path) -> PersistentTaskQueue:
    return PersistentTaskQueue(root / "runtime" / "genesis_tasks.sqlite3")


def _handoff(queue: PersistentTaskQueue, issue_number: int):
    task = queue.create(
        "Stale generic Issue task",
        module_id="genesis.security",
        payload={
            "task_type": "github_issue_development",
            "github_issue_number": issue_number,
        },
    )
    return queue.cancel(task.task_id, HANDOFF_REASON)


def _specialist(queue: PersistentTaskQueue, issue_number: int):
    return queue.create(
        "Issue-backed specialist task",
        module_id="genesis.research_tasks",
        payload={
            "task_type": "competitive_ai_improvement",
            "github_issue_number": issue_number,
            "github_issue_authoritative": True,
        },
    )


def _complete(queue: PersistentTaskQueue, task_id: str) -> None:
    queue.transition(task_id, "assigned")
    queue.transition(task_id, "running")
    queue.transition(task_id, "review")
    queue.transition(task_id, "complete")


def test_handoff_only_keeps_authoritative_issue_open(tmp_path: Path) -> None:
    queue = _queue(tmp_path)
    handoff = _handoff(queue, 340)
    github = FakeGithub(340)

    result = reconcile_terminal_github_issues(tmp_path, requester=github)

    assert result["closed"] == []
    assert result["eligible"] == []
    assert result["skipped_handoff"] == [
        {
            "github_issue_number": 340,
            "handoff_task_ids": [handoff.task_id],
            "reason": "awaiting_specialist_replacement",
        }
    ]
    assert github.issue["state"] == "open"
    assert not any(method == "PATCH" for method, _, _ in github.calls)


def test_handoff_with_active_specialist_replacement_stays_open(tmp_path: Path) -> None:
    queue = _queue(tmp_path)
    _handoff(queue, 341)
    specialist = _specialist(queue, 341)
    queue.transition(specialist.task_id, "assigned")
    queue.transition(specialist.task_id, "running")
    github = FakeGithub(341)

    result = reconcile_terminal_github_issues(tmp_path, requester=github)

    assert result["closed"] == []
    assert result["skipped_handoff"] == []
    assert result["skipped_active"][0]["github_issue_number"] == 341
    assert result["skipped_active"][0]["active_task_ids"] == [specialist.task_id]
    assert github.issue["state"] == "open"
    assert not any(method == "PATCH" for method, _, _ in github.calls)


def test_handoff_with_completed_specialist_replacement_closes_completed(tmp_path: Path) -> None:
    queue = _queue(tmp_path)
    handoff = _handoff(queue, 342)
    specialist = _specialist(queue, 342)
    _complete(queue, specialist.task_id)
    github = FakeGithub(342)

    result = reconcile_terminal_github_issues(tmp_path, requester=github)

    assert result["skipped_handoff"] == []
    assert result["closed"] == [
        {
            "github_issue_number": 342,
            "state_reason": "completed",
            "task_ids": [handoff.task_id, specialist.task_id],
        }
    ]
    assert github.issue["state"] == "closed"
    assert github.issue["state_reason"] == "completed"
