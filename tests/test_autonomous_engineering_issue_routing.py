from __future__ import annotations

from pathlib import Path

import scripts.autonomous_engineering as autonomous_engineering
from genesis.modules.task_queue import PersistentTaskQueue


def _self_improvement_issue(number: int = 340) -> dict:
    return {
        "number": number,
        "title": "[Genesis Self Improvement] competitive AI improvement",
        "body": (
            "Raise benchmark capability while preserving tests, Security, validation, "
            "protected files, signing, secrets, and owner control."
        ),
        "html_url": f"https://github.com/Maxhm007/Genesis-AI-Network/issues/{number}",
        "labels": [
            {"name": "genesis-self-improvement"},
            {"name": "genesis-task"},
        ],
    }


def _create_generic_issue_task(queue: PersistentTaskQueue, issue_number: int, suffix: str):
    return queue.create(
        f"Wrong generic task {suffix}",
        module_id="genesis.security",
        priority=90,
        payload={
            "task_type": "github_issue_development",
            "github_issue_number": issue_number,
            "source": "github_open_issue_backlog",
        },
    )


def test_self_improvement_label_wins_before_generic_security_heuristics():
    classification = autonomous_engineering.classify_open_issue(_self_improvement_issue())

    assert classification == {"kind": "issue_autorepair_specialist", "managed": True}


def test_specialist_intake_retires_stale_generic_task(monkeypatch, tmp_path: Path):
    queue = PersistentTaskQueue(tmp_path / "runtime" / "genesis_tasks.sqlite3")
    wrong = _create_generic_issue_task(queue, 340, "new")
    monkeypatch.setattr(autonomous_engineering, "_github_open_issues", lambda: [_self_improvement_issue()])

    result = autonomous_engineering.ingest_open_issue_backlog(tmp_path)

    row = result["issues"][0]
    assert row["kind"] == "issue_autorepair_specialist"
    assert row["status"] == "owned_by_specialist"
    assert row["task_id"] is None
    assert row["retired_generic_tasks"] == [wrong.task_id]
    assert queue.get(wrong.task_id).state == "cancelled"


def test_specialist_intake_never_cancels_running_generic_candidate(monkeypatch, tmp_path: Path):
    queue = PersistentTaskQueue(tmp_path / "runtime" / "genesis_tasks.sqlite3")
    running = _create_generic_issue_task(queue, 340, "running")
    queue.transition(running.task_id, to_state="assigned", reason="test assignment")
    queue.transition(running.task_id, to_state="running", reason="test execution")
    monkeypatch.setattr(autonomous_engineering, "_github_open_issues", lambda: [_self_improvement_issue()])

    result = autonomous_engineering.ingest_open_issue_backlog(tmp_path)

    assert result["issues"][0]["retired_generic_tasks"] == []
    assert queue.get(running.task_id).state == "running"
