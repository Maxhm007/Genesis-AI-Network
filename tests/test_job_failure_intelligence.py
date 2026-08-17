from datetime import datetime, timedelta, timezone
from pathlib import Path

from genesis.job_failure import JobFailureIntelligence
from genesis.modules.task_queue import PersistentTaskQueue
from genesis.task_router import TaskRouterModule


def _running_task(queue: PersistentTaskQueue, *, max_attempts: int = 3):
    task = queue.create("Repair an application job", module_id="genesis.application", max_attempts=max_attempts)
    queue.transition(task.task_id, "assigned")
    return queue.transition(task.task_id, "running")


def test_failure_history_and_exponential_retry_are_durable(tmp_path: Path):
    db = tmp_path / "tasks.sqlite3"
    queue = PersistentTaskQueue(db)
    task = _running_task(queue)

    failed = queue.record_failure(task.task_id, "provider timeout")
    assert failed.state == "failed"
    assert failed.attempt_count == 1
    assert failed.last_error == "provider timeout"
    assert failed.failure_history[0]["classification"] == "unknown"
    assert failed.next_retry_at is not None

    reopened = PersistentTaskQueue(db)
    restored = reopened.get(task.task_id)
    assert restored is not None
    assert restored.attempt_count == 1
    assert restored.failure_history == failed.failure_history


def test_exhausted_job_is_quarantined_instead_of_looping(tmp_path: Path):
    queue = PersistentTaskQueue(tmp_path / "tasks.sqlite3")
    task = _running_task(queue, max_attempts=2)

    first = queue.record_failure(task.task_id, "temporary network failure", retry_after_seconds=0)
    assert first.state == "failed"
    assert queue.retryable(first) is True

    queue.transition(task.task_id, "assigned")
    queue.transition(task.task_id, "running")
    second = queue.record_failure(task.task_id, "temporary network failure")
    assert second.state == "quarantined"
    assert second.attempt_count == 2
    assert queue.retryable(second) is False


def test_retryable_respects_backoff_window(tmp_path: Path):
    queue = PersistentTaskQueue(tmp_path / "tasks.sqlite3")
    task = _running_task(queue)
    failed = queue.record_failure(task.task_id, "rate limit", retry_after_seconds=600)

    now = datetime.now(timezone.utc)
    assert queue.retryable(failed, at=now) is False
    assert queue.retryable(failed, at=now + timedelta(minutes=11)) is True


def test_failure_intelligence_changes_strategy_after_dependency_failure(tmp_path: Path):
    router = TaskRouterModule(tmp_path)
    task = router.queue.create("Build desktop package", module_id="genesis.application")
    router.queue.transition(task.task_id, "assigned")
    router.queue.transition(task.task_id, "running")
    failed = router.queue.record_failure(
        task.task_id,
        "ImportError: missing dependency for packaging",
        classification="dependency",
        retry_after_seconds=0,
    )

    plan = JobFailureIntelligence.plan(failed)
    assert plan.classification == "dependency"
    assert plan.module_id == "genesis.coding"
    assert plan.use_ai_team is True

    routed = router.assign_next()
    assert routed["status"] == "assigned"
    assert routed["decision"]["module_id"] == "genesis.coding"
    assert routed["ai_team_module"] == "genesis.ai_team"
    assert routed["recovery_plan"]["action"] == "repair_dependency_then_retry"


def test_repeated_unknown_failure_recruits_specialist(tmp_path: Path):
    queue = PersistentTaskQueue(tmp_path / "tasks.sqlite3")
    task = _running_task(queue, max_attempts=4)
    first = queue.record_failure(task.task_id, "unexpected worker exit", retry_after_seconds=0)
    queue.transition(first.task_id, "assigned")
    queue.transition(first.task_id, "running")
    second = queue.record_failure(first.task_id, "unexpected worker exit", retry_after_seconds=0)

    plan = JobFailureIntelligence.plan(second)
    assert plan.action == "diagnose_with_ai_team"
    assert plan.use_ai_team is True
    assert plan.recruit_specialist is True
