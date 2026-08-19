from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from genesis.development_efficiency import DevelopmentEfficiencyGovernor
from genesis.modules.task_queue import PersistentTaskQueue


def _queue(tmp_path: Path) -> PersistentTaskQueue:
    return PersistentTaskQueue(tmp_path / "tasks.sqlite3")


def test_governor_prefers_fresh_high_yield_task_over_repeated_blocked_task(tmp_path: Path) -> None:
    queue = _queue(tmp_path)
    healthy = queue.create("Implement bounded capability improvement", module_id="genesis.coding", priority=70)
    blocked = queue.create("Retry old capability repair", module_id="genesis.ai_score", priority=95, max_attempts=5)
    queue.transition(blocked.task_id, "assigned", module_id="genesis.ai_score")
    queue.transition(blocked.task_id, "running", module_id="genesis.ai_score")
    queue.record_failure(blocked.task_id, "same regression", classification="validation", retry_after_seconds=0)
    blocked = queue.get(blocked.task_id)
    assert blocked is not None

    ranked = DevelopmentEfficiencyGovernor(queue).rank([blocked, healthy])
    assert ranked[0][0].task_id == healthy.task_id


def test_governor_skips_external_execution_blocker(tmp_path: Path) -> None:
    queue = _queue(tmp_path)
    task = queue.create("Run Terminal-Bench", module_id="genesis.coding", priority=100)
    queue.transition(task.task_id, "blocked", module_id="genesis.coding")
    with queue._connect() as db:
        db.execute(
            "UPDATE genesis_tasks SET state_reason = ? WHERE task_id = ?",
            ("external_execution_required: Harbor credential and sandbox configuration missing", task.task_id),
        )
    task = queue.get(task.task_id)
    assert task is not None
    decision = DevelopmentEfficiencyGovernor(queue).score(task)
    assert decision.eligible is False
    assert decision.reason == "external_or_owner_blocker"


def test_governor_respects_retry_cooldown(tmp_path: Path) -> None:
    queue = _queue(tmp_path)
    task = queue.create("Repair transient failure", module_id="genesis.coding", priority=90)
    queue.transition(task.task_id, "assigned", module_id="genesis.coding")
    queue.transition(task.task_id, "running", module_id="genesis.coding")
    queue.record_failure(task.task_id, "provider temporarily unavailable", classification="provider", retry_after_seconds=3600)
    task = queue.get(task.task_id)
    assert task is not None
    decision = DevelopmentEfficiencyGovernor(queue).score(task, at=datetime.now(timezone.utc))
    assert decision.eligible is False
    assert decision.reason == "retry_cooldown_active"


def test_governor_keeps_security_work_high_priority(tmp_path: Path) -> None:
    queue = _queue(tmp_path)
    security = queue.create("Repair high severity finding", module_id="genesis.security", priority=80)
    feature = queue.create("Improve UI", module_id="genesis.application", priority=95)
    ranked = DevelopmentEfficiencyGovernor(queue).rank([feature, security], at=datetime.now(timezone.utc) + timedelta(hours=1))
    assert ranked[0][0].task_id == security.task_id
