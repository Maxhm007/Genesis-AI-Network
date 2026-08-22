from __future__ import annotations

from dataclasses import dataclass

from genesis.agentic import AgenticPulseController


@dataclass(frozen=True)
class _Record:
    task_id: str
    stage: str
    target_path: str = "genesis/example.py"
    updated_at: str = "2026-08-22T00:00:00+00:00"


class _Store:
    def __init__(self, records):
        self.records = list(records)

    def list_active(self):
        return list(self.records)


class _Pipeline:
    def __init__(self, records):
        self.store = _Store(records)


def test_plan_prioritizes_executable_review_over_validation_wait(tmp_path):
    controller = AgenticPulseController(tmp_path, "gene-test")
    pipeline = _Pipeline(
        [
            _Record("validate-me", "validation_ready", "genesis/old.py"),
            _Record("review-me", "review_ready", "genesis/new.py"),
        ]
    )

    plan = controller.plan(pipeline)

    assert plan.goal_id == "pipeline:review-me"
    assert plan.next_action == "review_candidate"
    assert plan.specialist == "review"
    assert "genesis/new.py" in plan.objective


def test_failure_observation_replans_same_goal_and_persists(tmp_path):
    pipeline = _Pipeline([_Record("repair-me", "needs_repair")])
    controller = AgenticPulseController(tmp_path, "gene-test")
    first_plan = controller.plan(pipeline)
    assert first_plan.strategy == "advance_highest_priority_bounded_step"

    agentic = controller.observe(
        {
            "action": "pipeline_repair_retry",
            "pipeline": {
                "record": {
                    "task_id": "repair-me",
                    "stage": "needs_repair",
                }
            },
        }
    )

    assert agentic["observation"]["classification"] == "failure"
    assert agentic["metrics"]["failure_events"] == 1
    assert agentic["metrics"]["replans"] == 1

    reloaded = AgenticPulseController(tmp_path, "gene-test")
    next_plan = reloaded.plan(pipeline)
    assert next_plan.goal_id == "pipeline:repair-me"
    assert next_plan.strategy == "use_feedback_and_retry_same_goal"
    assert reloaded.snapshot()["metrics"]["steps"] == 1


def test_repeated_neutral_observation_detects_stall_and_replans(tmp_path):
    controller = AgenticPulseController(tmp_path, "gene-test")
    controller.plan(_Pipeline([]))
    result = {"action": "pipeline_discovery_continue", "decision": {"task_id": None}}

    first = controller.observe(result)
    second = controller.observe(result)
    third = controller.observe(result)

    assert first["observation"]["classification"] == "neutral"
    assert second["observation"]["classification"] == "neutral"
    assert third["observation"]["classification"] == "stalled"
    assert third["metrics"]["stall_events"] == 1
    assert third["metrics"]["replans"] == 1
    assert third["plan"]["strategy"] == "reassess_worker_and_evidence_before_retry"


def test_no_active_task_creates_continuous_self_improvement_goal(tmp_path):
    controller = AgenticPulseController(tmp_path, "gene-test")

    plan = controller.plan(_Pipeline([]))

    assert plan.goal_id == "genesis:self-improvement"
    assert plan.next_action == "discover_or_learn"
    assert plan.specialist == "discovery"
