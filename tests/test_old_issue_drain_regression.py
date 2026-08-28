from __future__ import annotations

from pathlib import Path

from genesis.efficient_engineering import EfficientAutonomousEngineeringLoop


def _issue_task(loop, key: str, issue: int, *, generation: int = 1, priority: int = 95):
    task, _ = loop.queue.create_unique(
        key,
        f"Resolve GitHub issue #{issue}.",
        module_id="genesis.self_development",
        priority=priority,
        payload={
            "task_type": "github_issue_development",
            "github_issue_number": issue,
            "work_generation": generation,
        },
    )
    return task


def test_old_issue_keeps_age_across_retry_generations(tmp_path: Path):
    loop = EfficientAutonomousEngineeringLoop(tmp_path)
    old = _issue_task(loop, "old-109-generation-5", 109, generation=5)
    _issue_task(loop, "new-348-generation-1", 348, generation=1)
    selected = loop._select_task()
    assert selected is not None
    assert selected.task_id == old.task_id
    assert loop._selection_trace[-1]["reason"] == "github_issue_fair_rotation"


def test_priority_100_emergency_can_preempt_old_issue(tmp_path: Path):
    loop = EfficientAutonomousEngineeringLoop(tmp_path)
    _issue_task(loop, "old-normal-109", 109, generation=5, priority=95)
    emergency = _issue_task(loop, "new-critical-500", 500, generation=1, priority=100)
    selected = loop._select_task()
    assert selected is not None
    assert selected.task_id == emergency.task_id


def test_old_issue_is_visible_beyond_legacy_top_100_priority_window(tmp_path: Path):
    loop = EfficientAutonomousEngineeringLoop(tmp_path)
    old = _issue_task(loop, "old-visible-109", 109, generation=5, priority=90)
    for number in range(300, 425):
        _issue_task(loop, f"newer-{number}", number, generation=1, priority=96)
    selected = loop._select_task()
    assert selected is not None
    assert selected.task_id == old.task_id
