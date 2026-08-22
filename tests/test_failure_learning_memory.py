from pathlib import Path

from genesis.autonomous_engineering import AutonomousEngineeringLoop


def _loop(tmp_path: Path) -> AutonomousEngineeringLoop:
    root = tmp_path / "repo"
    root.mkdir()
    (root / "runtime").mkdir()
    return AutonomousEngineeringLoop(root)


def test_failure_learning_includes_same_task_retry_history(tmp_path):
    loop = _loop(tmp_path)
    task = loop.queue.create(
        "Improve capability safely",
        module_id="genesis.ai_score",
        payload={"issue_key": "ai-gap", "work_generation": 1},
        max_attempts=3,
    )
    loop.queue.transition(task.task_id, "assigned", module_id="genesis.ai_score")
    failed = loop.queue.record_failure(
        task.task_id,
        "tests failed because benchmark evidence was synthetic",
        classification="pipeline_development",
        retry_after_seconds=0,
        module_id="genesis.ai_score",
    )

    context = loop._failure_learning_context(failed)

    assert "tests failed because benchmark evidence was synthetic" in context
    assert failed.task_id in context
    assert '"work_generation": 1' in context


def test_failure_learning_transfers_across_operational_generations(tmp_path):
    loop = _loop(tmp_path)
    first = loop.queue.create(
        "Resolve recurring capability gap",
        module_id="genesis.ai_score",
        payload={"issue_key": "same-operational-issue", "work_generation": 1},
        max_attempts=1,
    )
    loop.queue.transition(first.task_id, "assigned", module_id="genesis.ai_score")
    quarantined = loop.queue.record_failure(
        first.task_id,
        "review rejected architecture-only score inflation",
        classification="internal_development_review",
        retry_after_seconds=0,
        module_id="genesis.ai_score",
    )
    assert quarantined.state == "quarantined"

    second = loop.queue.create(
        "Resolve recurring capability gap",
        module_id="genesis.ai_score",
        payload={"issue_key": "same-operational-issue", "work_generation": 2},
        max_attempts=3,
    )

    context = loop._failure_learning_context(second)

    assert quarantined.task_id in context
    assert "review rejected architecture-only score inflation" in context
    assert '"work_generation": 1' in context


def test_failure_learning_does_not_leak_unrelated_issue_history(tmp_path):
    loop = _loop(tmp_path)
    unrelated = loop.queue.create(
        "Fix unrelated issue",
        module_id="genesis.ai_score",
        payload={"issue_key": "issue-a", "work_generation": 1},
        max_attempts=1,
    )
    loop.queue.transition(unrelated.task_id, "assigned", module_id="genesis.ai_score")
    loop.queue.record_failure(
        unrelated.task_id,
        "secret lesson for issue A",
        classification="pipeline_repair",
        retry_after_seconds=0,
        module_id="genesis.ai_score",
    )

    target = loop.queue.create(
        "Fix target issue",
        module_id="genesis.ai_score",
        payload={"issue_key": "issue-b", "work_generation": 1},
        max_attempts=3,
    )

    context = loop._failure_learning_context(target)

    assert "secret lesson for issue A" not in context
