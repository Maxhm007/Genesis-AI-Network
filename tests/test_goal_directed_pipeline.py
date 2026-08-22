from __future__ import annotations

from dataclasses import dataclass

from genesis.goal_directed_pipeline import GoalDirectedPipelineCoordinator


@dataclass(frozen=True)
class _Record:
    task_id: str
    stage: str


class _Store:
    def __init__(self, records):
        self.records = list(records)

    def list_active(self):
        return list(self.records)

    def get(self, task_id):
        return next((record for record in self.records if record.task_id == task_id), None)


class _Worker:
    def __init__(self, action):
        self.action = action
        self.seen = []

    def run(self, record):
        self.seen.append(record.task_id)
        return {
            "action": self.action,
            "record": {"task_id": record.task_id, "stage": record.stage},
        }


def _coordinator(records):
    coordinator = object.__new__(GoalDirectedPipelineCoordinator)
    coordinator.store = _Store(records)
    coordinator.learning = _Worker("pipeline_learning_completed")
    coordinator.review = _Worker("pipeline_internal_review_approved")
    coordinator.development = _Worker("pipeline_development_completed")
    coordinator.repair = _Worker("pipeline_repair_completed")
    coordinator.triage = _Worker("pipeline_triaged")
    coordinator.validation = _Worker("pipeline_wait_validation")
    coordinator._recover_orphan_review = lambda: None
    return coordinator


def test_preferred_goal_task_controls_next_bounded_worker():
    coordinator = _coordinator(
        [
            _Record("repair-a", "needs_repair"),
            _Record("review-b", "review_ready"),
        ]
    )

    result = coordinator.run_once(preferred_task_id="repair-a")

    assert result["handled"] is True
    assert result["goal_directed"] is True
    assert result["preferred_task_id"] == "repair-a"
    assert result["action"] == "pipeline_repair_completed"
    assert coordinator.repair.seen == ["repair-a"]
    assert coordinator.review.seen == []


def test_recovered_review_preempts_unrelated_preferred_goal():
    coordinator = _coordinator([_Record("repair-a", "needs_repair")])

    def recover():
        recovered = _Record("recovered-review", "review_ready")
        coordinator.store.records.append(recovered)
        return {
            "status": "orphan_review_recovered",
            "task_id": recovered.task_id,
            "candidate_sha": "a" * 40,
            "review_ref": "genesis/review-aaaaaaaaaaaa",
        }

    coordinator._recover_orphan_review = recover

    result = coordinator.run_once(preferred_task_id="repair-a")

    assert result["handled"] is True
    assert result["action"] == "pipeline_internal_review_approved"
    assert result["goal_directed"] is False
    assert result["preferred_task_id"] == "repair-a"
    assert result["orphan_review_recovery"]["task_id"] == "recovered-review"
    assert coordinator.review.seen == ["recovered-review"]
    assert coordinator.repair.seen == []


def test_goal_selected_validation_still_uses_canonical_validator_worker():
    coordinator = _coordinator([_Record("validate-me", "validation_ready")])

    result = coordinator.run_once(preferred_task_id="validate-me")

    assert result["handled"] is True
    assert result["goal_directed"] is True
    assert result["action"] == "pipeline_wait_validation"
    assert coordinator.validation.seen == ["validate-me"]


def test_unknown_preference_falls_back_to_bounded_scheduler(monkeypatch):
    coordinator = _coordinator([_Record("repair-a", "needs_repair")])

    def fallback(self):
        return {"handled": True, "action": "fallback"}

    monkeypatch.setattr(
        "genesis.bounded_autonomy_pipeline.BoundedAutonomyPipelineCoordinator.run_once",
        fallback,
    )

    result = coordinator.run_once(preferred_task_id="missing")

    assert result["action"] == "fallback"
    assert result["goal_directed"] is False
    assert result["preferred_task_id"] == "missing"
