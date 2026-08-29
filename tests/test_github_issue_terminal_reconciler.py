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


def _fail(queue: PersistentTaskQueue, task_id: str) -> None:
    queue.transition(task_id, "assigned")
    queue.record_failure(task_id, "bounded failure", retry_after_seconds=0)


def _issue(number: int, *, title: str = "Repair defect", labels: list[dict] | None = None) -> dict:
    return {
        "number": number,
        "title": title,
        "state": "open",
        "labels": labels if labels is not None else [{"name": "genesis-task"}],
    }


def test_completed_issue_backed_task_closes_issue(tmp_path: Path) -> None:
    queue = _queue(tmp_path)
    task, _ = queue.create_unique(
        "terminal-close",
        "Repair the issue and close it after verified completion",
        payload={"task_type": "github_issue_development", "github_issue_number": 42},
    )
    _complete(queue, task.task_id)
    github = FakeGithub([_issue(42)])

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
    github = FakeGithub([_issue(77, title="Shared task")])

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
    github = FakeGithub([_issue(88, title="Superseded task")])

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
        _issue(
            4,
            title="Genesis Control: hourly autonomous report",
            labels=[{"name": "genesis-persistent"}],
        )
    ])

    result = reconcile_terminal_github_issues(tmp_path, requester=github)

    assert result["skipped_protected"] == [4]
    assert result["closed"] == []
    assert github.issues[4]["state"] == "open"


def test_failed_older_generation_is_cancelled_after_newer_generation_completes(tmp_path: Path) -> None:
    queue = _queue(tmp_path)
    old, _ = queue.create_unique(
        "issue-90-generation-1",
        "Older failed generation",
        payload={
            "github_issue_number": 90,
            "problem_fingerprint": "terminal-reconcile:90",
            "work_generation": 1,
        },
    )
    newer, _ = queue.create_unique(
        "issue-90-generation-2",
        "Replacement generation",
        payload={
            "github_issue_number": 90,
            "problem_fingerprint": "terminal-reconcile:90",
            "work_generation": 2,
        },
    )
    _fail(queue, old.task_id)
    _complete(queue, newer.task_id)
    github = FakeGithub([_issue(90)])

    result = reconcile_terminal_github_issues(tmp_path, requester=github)

    old_after = queue.get(old.task_id)
    assert old_after is not None and old_after.state == "cancelled"
    assert "work_generation 2" in str(old_after.state_reason)
    assert result["superseded"][0]["task_id"] == old.task_id
    assert result["closed"][0]["github_issue_number"] == 90
    assert result["closed"][0]["state_reason"] == "completed"
    assert github.issues[90]["state"] == "closed"


def test_current_failed_generation_without_replacement_stays_open(tmp_path: Path) -> None:
    queue = _queue(tmp_path)
    current, _ = queue.create_unique(
        "issue-91-generation-2",
        "Current failed generation",
        payload={
            "github_issue_number": 91,
            "problem_fingerprint": "terminal-reconcile:91",
            "work_generation": 2,
        },
    )
    _fail(queue, current.task_id)
    github = FakeGithub([_issue(91)])

    result = reconcile_terminal_github_issues(tmp_path, requester=github)

    assert result["superseded"] == []
    assert result["closed"] == []
    assert result["skipped_active"][0]["active_task_ids"] == [current.task_id]
    assert queue.get(current.task_id).state == "failed"
    assert not any(method == "PATCH" for method, _, _ in github.calls)


def test_newer_running_generation_keeps_issue_open_after_old_failure_is_superseded(tmp_path: Path) -> None:
    queue = _queue(tmp_path)
    old, _ = queue.create_unique(
        "issue-92-generation-1",
        "Old failed generation",
        payload={
            "github_issue_number": 92,
            "problem_fingerprint": "terminal-reconcile:92",
            "work_generation": 1,
        },
    )
    current, _ = queue.create_unique(
        "issue-92-generation-2",
        "Current running generation",
        payload={
            "github_issue_number": 92,
            "problem_fingerprint": "terminal-reconcile:92",
            "work_generation": 2,
        },
    )
    _fail(queue, old.task_id)
    queue.transition(current.task_id, "assigned")
    queue.transition(current.task_id, "running")
    github = FakeGithub([_issue(92)])

    result = reconcile_terminal_github_issues(tmp_path, requester=github)

    assert queue.get(old.task_id).state == "cancelled"
    assert queue.get(current.task_id).state == "running"
    assert result["closed"] == []
    assert result["skipped_active"][0]["active_task_ids"] == [current.task_id]
    assert github.issues[92]["state"] == "open"
    assert not any(method == "PATCH" for method, _, _ in github.calls)


def test_different_lineages_on_same_issue_do_not_supersede_each_other(tmp_path: Path) -> None:
    queue = _queue(tmp_path)
    old, _ = queue.create_unique(
        "issue-93-lineage-a",
        "Failed work from lineage A",
        payload={
            "github_issue_number": 93,
            "problem_fingerprint": "lineage:a",
            "work_generation": 1,
        },
    )
    newer, _ = queue.create_unique(
        "issue-93-lineage-b",
        "Completed work from lineage B",
        payload={
            "github_issue_number": 93,
            "problem_fingerprint": "lineage:b",
            "work_generation": 2,
        },
    )
    _fail(queue, old.task_id)
    _complete(queue, newer.task_id)
    github = FakeGithub([_issue(93)])

    result = reconcile_terminal_github_issues(tmp_path, requester=github)

    assert result["superseded"] == []
    assert result["closed"] == []
    assert queue.get(old.task_id).state == "failed"
    assert github.issues[93]["state"] == "open"


def test_explicit_supersedes_task_id_retires_queued_older_task(tmp_path: Path) -> None:
    queue = _queue(tmp_path)
    old, _ = queue.create_unique(
        "issue-94-old",
        "Older queued generation",
        payload={"github_issue_number": 94},
    )
    queue.transition(old.task_id, "assigned")
    newer, _ = queue.create_unique(
        "issue-94-new",
        "Explicit replacement",
        payload={
            "github_issue_number": 94,
            "supersedes_task_id": old.task_id,
        },
    )
    _complete(queue, newer.task_id)
    github = FakeGithub([_issue(94)])

    result = reconcile_terminal_github_issues(tmp_path, requester=github)

    old_after = queue.get(old.task_id)
    assert old_after is not None and old_after.state == "cancelled"
    assert old_after.state_reason == f"explicitly superseded by {newer.task_id}"
    assert result["closed"][0]["github_issue_number"] == 94


def test_explicit_supersession_never_interrupts_running_or_review_work(tmp_path: Path) -> None:
    queue = _queue(tmp_path)
    old, _ = queue.create_unique(
        "issue-95-running",
        "Running work",
        payload={"github_issue_number": 95},
    )
    queue.transition(old.task_id, "assigned")
    queue.transition(old.task_id, "running")
    newer, _ = queue.create_unique(
        "issue-95-replacement",
        "Replacement that must not interrupt live work",
        payload={
            "github_issue_number": 95,
            "supersedes_task_id": old.task_id,
        },
    )
    _complete(queue, newer.task_id)
    github = FakeGithub([_issue(95)])

    result = reconcile_terminal_github_issues(tmp_path, requester=github)

    assert result["superseded"] == []
    assert result["closed"] == []
    assert queue.get(old.task_id).state == "running"
    assert github.issues[95]["state"] == "open"


def test_protected_issue_does_not_cancel_superseded_history(tmp_path: Path) -> None:
    queue = _queue(tmp_path)
    old, _ = queue.create_unique(
        "issue-96-generation-1",
        "Old failed protected generation",
        payload={
            "github_issue_number": 96,
            "problem_fingerprint": "protected:96",
            "work_generation": 1,
        },
    )
    newer, _ = queue.create_unique(
        "issue-96-generation-2",
        "New completed protected generation",
        payload={
            "github_issue_number": 96,
            "problem_fingerprint": "protected:96",
            "work_generation": 2,
        },
    )
    _fail(queue, old.task_id)
    _complete(queue, newer.task_id)
    github = FakeGithub([
        _issue(96, title="Genesis Control: protected channel", labels=[{"name": "genesis-control"}])
    ])

    result = reconcile_terminal_github_issues(tmp_path, requester=github)

    assert result["skipped_protected"] == [96]
    assert result["superseded"] == []
    assert result["closed"] == []
    assert queue.get(old.task_id).state == "failed"
    assert github.issues[96]["state"] == "open"


def test_repeated_reconciliation_is_idempotent_after_supersession(tmp_path: Path) -> None:
    queue = _queue(tmp_path)
    old, _ = queue.create_unique(
        "issue-97-generation-1",
        "Old failed generation",
        payload={
            "github_issue_number": 97,
            "problem_fingerprint": "terminal-reconcile:97",
            "work_generation": 1,
        },
    )
    newer, _ = queue.create_unique(
        "issue-97-generation-2",
        "Completed replacement generation",
        payload={
            "github_issue_number": 97,
            "problem_fingerprint": "terminal-reconcile:97",
            "work_generation": 2,
        },
    )
    _fail(queue, old.task_id)
    _complete(queue, newer.task_id)
    github = FakeGithub([_issue(97)])

    first = reconcile_terminal_github_issues(tmp_path, requester=github)
    second = reconcile_terminal_github_issues(tmp_path, requester=github)

    assert len(first["superseded"]) == 1
    assert first["closed"][0]["github_issue_number"] == 97
    assert second["superseded"] == []
    assert second["already_closed"] == [97]
    patches = [call for call in github.calls if call[0] == "PATCH"]
    assert len(patches) == 1
