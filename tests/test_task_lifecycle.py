from datetime import datetime, timedelta, timezone
import json
from pathlib import Path

from genesis.task_lifecycle import TaskLifecycleReconciler


def _make_review_task(root: Path):
    reconciler = TaskLifecycleReconciler(root)
    task = reconciler.queue.create(
        "repair measured operational issue",
        module_id="genesis.ai_score",
        payload={"task_type": "operational_issue"},
    )
    reconciler.queue.transition(task.task_id, "assigned")
    reconciler.queue.transition(task.task_id, "running")
    return reconciler.queue.transition(task.task_id, "review")


def test_promoted_review_becomes_complete(tmp_path: Path, monkeypatch):
    task = _make_review_task(tmp_path)
    runtime = tmp_path / "runtime"
    (runtime / "autonomous_engineering.json").write_text(
        json.dumps({
            "attempted_tasks": [{
                "task": {"task_id": task.task_id},
                "candidate": {"commit_sha": "abc123"},
            }]
        }),
        encoding="utf-8",
    )
    reconciler = TaskLifecycleReconciler(tmp_path)
    monkeypatch.setattr(reconciler, "_is_ancestor", lambda sha: sha == "abc123")
    result = reconciler.reconcile()
    assert task.task_id in result["completed"]
    assert reconciler.queue.get(task.task_id).state == "complete"


def test_stale_unpromoted_review_becomes_retryable_failure(tmp_path: Path):
    task = _make_review_task(tmp_path)
    reconciler = TaskLifecycleReconciler(tmp_path)
    old = (datetime.now(timezone.utc) - timedelta(hours=4)).isoformat()
    with reconciler.queue._connect() as db:
        db.execute("UPDATE genesis_tasks SET updated_at = ? WHERE task_id = ?", (old, task.task_id))
    result = reconciler.reconcile()
    updated = reconciler.queue.get(task.task_id)
    assert task.task_id in result["retried"]
    assert updated.state == "failed"
    assert reconciler.queue.retryable(updated)
