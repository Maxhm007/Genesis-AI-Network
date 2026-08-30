from __future__ import annotations

from pathlib import Path

from genesis.modules.task_queue import PersistentTaskQueue
from scripts.specialist_handoff_gate import inspect_pending_specialist_handoffs


HANDOFF_REASON = "issue_route_migrated_to_self_improvement_specialist"


def _queue(root: Path) -> PersistentTaskQueue:
    return PersistentTaskQueue(root / "runtime" / "genesis_tasks.sqlite3")


def _handoff(queue: PersistentTaskQueue, issue_number: int):
    task, _ = queue.create_unique(
        f"handoff-gate-{issue_number}",
        "Generic task handed to specialist lane",
        module_id="genesis.security",
        payload={"task_type": "github_issue_development", "github_issue_number": issue_number},
    )
    return queue.cancel(task.task_id, HANDOFF_REASON)


def _generic_history(queue: PersistentTaskQueue, issue_number: int):
    task, _ = queue.create_unique(
        f"history-gate-{issue_number}",
        "Historical generic task",
        module_id="genesis.security",
        payload={"task_type": "github_issue_development", "github_issue_number": issue_number},
    )
    return queue.cancel(task.task_id, "historical generic generation ended")


def _specialist(queue: PersistentTaskQueue, issue_number: int):
    task, _ = queue.create_unique(
        f"specialist-gate-{issue_number}",
        "Specialist replacement",
        module_id="genesis.capability",
        payload={"task_type": "competitive_ai_improvement", "github_issue_number": issue_number},
    )
    return task


def test_pending_handoff_detected_even_with_old_generic_history(tmp_path: Path) -> None:
    queue = _queue(tmp_path)
    _generic_history(queue, 340)
    handoff = _handoff(queue, 340)

    result = inspect_pending_specialist_handoffs(tmp_path)

    assert result["pending"] is True
    assert result["pending_count"] == 1
    assert result["handoffs"] == [
        {
            "github_issue_number": 340,
            "handoff_task_ids": [handoff.task_id],
            "reason": "awaiting_specialist_replacement",
        }
    ]


def test_real_specialist_replacement_suppresses_handoff_yield(tmp_path: Path) -> None:
    queue = _queue(tmp_path)
    _handoff(queue, 340)
    _specialist(queue, 340)

    result = inspect_pending_specialist_handoffs(tmp_path)

    assert result["pending"] is False
    assert result["pending_count"] == 0
    assert result["handoffs"] == []


def test_no_handoff_does_not_request_proactive_yield(tmp_path: Path) -> None:
    queue = _queue(tmp_path)
    _generic_history(queue, 350)

    result = inspect_pending_specialist_handoffs(tmp_path)

    assert result["pending"] is False
    assert result["pending_count"] == 0
