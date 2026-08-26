from __future__ import annotations

from pathlib import Path

from genesis.efficient_engineering import EfficientAutonomousEngineeringLoop


def _generic_issue(loop: EfficientAutonomousEngineeringLoop, number: int, *, generation: int = 1):
    task, _ = loop.queue.create_unique(
        f"github-open-issue:{number}:generation:{generation}",
        f"Advance complete resolution of GitHub issue #{number}.",
        module_id="genesis.self_development",
        priority=90,
        max_attempts=5,
        payload={
            "task_type": "github_issue_development",
            "github_issue_number": number,
            "work_generation": generation,
        },
    )
    return task


def _devlab_issue(loop: EfficientAutonomousEngineeringLoop, number: int, *, generation: int = 1):
    task, _ = loop.queue.create_unique(
        f"github-devlab-issue:{number}:generation:{generation}",
        f"Resolve bounded DevLab GitHub issue #{number}.",
        module_id="genesis.coding",
        priority=95,
        max_attempts=5,
        payload={
            "task_type": "devlab_issue",
            "executor": "genesis.devlab",
            "github_issue_number": number,
            "work_generation": generation,
            "target_path": "genesis/resource.py",
        },
    )
    return task


def _fail_now(loop: EfficientAutonomousEngineeringLoop, task) -> None:
    loop.queue.transition(task.task_id, "assigned", module_id=task.module_id)
    loop.queue.transition(task.task_id, "running", module_id=task.module_id)
    loop.queue.record_failure(
        task.task_id,
        "bounded test failure",
        classification="test",
        retry_after_seconds=0,
        module_id=task.module_id,
    )


def test_older_untouched_issue_runs_before_newer_devlab_issue(tmp_path: Path):
    loop = EfficientAutonomousEngineeringLoop(tmp_path)
    older = _generic_issue(loop, 60)
    newer_devlab = _devlab_issue(loop, 109)

    selected = loop._select_task()

    assert selected is not None
    assert selected.task_id == older.task_id
    assert selected.task_id != newer_devlab.task_id
    assert loop._selection_trace[-1]["reason"] == "github_issue_fair_rotation"
    assert loop._selection_trace[-1]["issue_number"] == 60


def test_failed_issue_retry_rotates_behind_other_open_issue(tmp_path: Path):
    loop = EfficientAutonomousEngineeringLoop(tmp_path)
    older = _generic_issue(loop, 60)
    newer_devlab = _devlab_issue(loop, 109)

    first = loop._select_task()
    assert first is not None and first.task_id == older.task_id
    _fail_now(loop, first)

    second = loop._select_task()
    assert second is not None and second.task_id == newer_devlab.task_id
    _fail_now(loop, second)

    third = loop._select_task()
    assert third is not None and third.task_id == older.task_id


def test_retry_generation_does_not_jump_a_never_attempted_older_issue(tmp_path: Path):
    loop = EfficientAutonomousEngineeringLoop(tmp_path)
    retry_generation = _devlab_issue(loop, 109, generation=2)
    untouched_older = _generic_issue(loop, 60, generation=1)

    selected = loop._select_task()

    assert selected is not None
    assert selected.task_id == untouched_older.task_id
    assert selected.task_id != retry_generation.task_id
