from __future__ import annotations

from pathlib import Path

from genesis.github_issue_authority_reconciler import reconcile_closed_github_issue_tasks
from genesis.modules.task_queue import PersistentTaskQueue


class FakeGithub:
    def __init__(self, issues: list[dict]) -> None:
        self.issues = {int(issue["number"]): dict(issue) for issue in issues}
        self.calls: list[tuple[str, str, dict | None]] = []

    def __call__(self, method: str, path: str, payload: dict | None = None):
        self.calls.append((method, path, payload))
        if method == "GET" and path.startswith("/issues/"):
            return self.issues.get(int(path.rsplit("/", 1)[1]))
        return None


def _queue(root: Path) -> PersistentTaskQueue:
    return PersistentTaskQueue(root / "runtime" / "genesis_tasks.sqlite3")


def _task(queue: PersistentTaskQueue, key: str, issue: int, state: str):
    task, _ = queue.create_unique(
        key,
        f"Issue #{issue} cached work",
        module_id="genesis.coding",
        payload={"github_issue_number": issue, "task_type": "github_issue_development"},
        max_attempts=4,
    )
    if state == "new":
        return task
    if state == "assigned":
        return queue.transition(task.task_id, "assigned")
    if state == "running":
        queue.transition(task.task_id, "assigned")
        return queue.transition(task.task_id, "running")
    if state == "paused":
        return queue.pause(task.task_id, "waiting")
    if state == "blocked":
        return queue.transition(task.task_id, "blocked")
    if state == "review":
        queue.transition(task.task_id, "assigned")
        queue.transition(task.task_id, "running")
        return queue.transition(task.task_id, "review")
    if state == "failed":
        queue.transition(task.task_id, "assigned")
        return queue.record_failure(task.task_id, "retry me", retry_after_seconds=0)
    if state == "quarantined":
        terminal, _ = queue.create_unique(
            key + ":quarantine",
            f"Issue #{issue} quarantined cached work",
            module_id="genesis.coding",
            payload={"github_issue_number": issue, "task_type": "github_issue_development"},
            max_attempts=1,
        )
        queue.transition(terminal.task_id, "assigned")
        return queue.record_failure(terminal.task_id, "budget exhausted", retry_after_seconds=0)
    if state == "complete":
        queue.transition(task.task_id, "assigned")
        queue.transition(task.task_id, "running")
        queue.transition(task.task_id, "review")
        return queue.transition(task.task_id, "complete")
    if state == "cancelled":
        return queue.cancel(task.task_id, "already closed")
    raise AssertionError(state)


def test_closed_issue_cancels_every_nonterminal_cached_state(tmp_path: Path) -> None:
    queue = _queue(tmp_path)
    states = ["new", "assigned", "running", "paused", "blocked", "review", "failed", "quarantined"]
    tasks = [_task(queue, f"closed-{state}", 701, state) for state in states]
    github = FakeGithub([{"number": 701, "state": "closed", "state_reason": "not_planned"}])

    result = reconcile_closed_github_issue_tasks(tmp_path, open_issue_numbers=set(), requester=github)

    assert result["status"] == "ok"
    assert result["confirmed_closed"] == [{"github_issue_number": 701, "state_reason": "not_planned"}]
    assert len(result["cancelled"]) == len(states)
    for task in tasks:
        current = queue.get(task.task_id)
        assert current is not None
        assert current.state == "cancelled"
        assert "Issue #701 closed (not_planned)" in (current.state_reason or "")


def test_open_issue_snapshot_never_cancels_cached_work(tmp_path: Path) -> None:
    queue = _queue(tmp_path)
    task = _task(queue, "open-702", 702, "failed")
    github = FakeGithub([{"number": 702, "state": "open", "state_reason": None}])

    result = reconcile_closed_github_issue_tasks(tmp_path, open_issue_numbers={702}, requester=github)

    assert result["status"] == "ok"
    assert result["skipped_open"] == [702]
    assert result["cancelled"] == []
    assert queue.get(task.task_id).state == "failed"
    assert github.calls == []


def test_snapshot_miss_is_confirmed_before_cancellation(tmp_path: Path) -> None:
    queue = _queue(tmp_path)
    task = _task(queue, "still-open-703", 703, "new")
    github = FakeGithub([{"number": 703, "state": "open", "state_reason": None}])

    result = reconcile_closed_github_issue_tasks(tmp_path, open_issue_numbers=set(), requester=github)

    assert result["status"] == "ok"
    assert result["cancelled"] == []
    assert result["skipped_open"] == [703]
    assert queue.get(task.task_id).state == "new"
    assert github.calls == [("GET", "/issues/703", None)]


def test_unavailable_issue_fails_closed_without_mutating_task(tmp_path: Path) -> None:
    queue = _queue(tmp_path)
    task = _task(queue, "unavailable-704", 704, "running")
    github = FakeGithub([])

    result = reconcile_closed_github_issue_tasks(tmp_path, open_issue_numbers=set(), requester=github)

    assert result["status"] == "blocked"
    assert result["blocked"][0]["github_issue_number"] == 704
    assert queue.get(task.task_id).state == "running"


def test_terminal_rows_are_idempotent_and_not_reprocessed(tmp_path: Path) -> None:
    queue = _queue(tmp_path)
    complete = _task(queue, "complete-705", 705, "complete")
    cancelled = _task(queue, "cancelled-705", 705, "cancelled")
    github = FakeGithub([{"number": 705, "state": "closed", "state_reason": "completed"}])

    first = reconcile_closed_github_issue_tasks(tmp_path, open_issue_numbers=set(), requester=github)
    second = reconcile_closed_github_issue_tasks(tmp_path, open_issue_numbers=set(), requester=github)

    assert first["linked_nonterminal_issue_count"] == 0
    assert second["linked_nonterminal_issue_count"] == 0
    assert first["cancelled"] == second["cancelled"] == []
    assert queue.get(complete.task_id).state == "complete"
    assert queue.get(cancelled.task_id).state == "cancelled"
    assert github.calls == []
