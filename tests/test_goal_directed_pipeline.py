from __future__ import annotations

from dataclasses import dataclass, replace

from genesis.goal_directed_pipeline import GoalDirectedPipelineCoordinator


@dataclass(frozen=True)
class _Record:
    task_id: str
    stage: str
    candidate_sha: str | None = None
    review_ref: str | None = None
    updated_at: str = ""
    last_feedback: str | None = None
    discovery: dict | None = None


@dataclass(frozen=True)
class _Task:
    task_id: str
    state: str
    payload: dict
    state_reason: str | None = None


class _Queue:
    def __init__(self, tasks):
        self.tasks = {task.task_id: task for task in tasks}
        self.cancelled = []

    def get(self, task_id):
        return self.tasks.get(task_id)

    def cancel(self, task_id, reason):
        task = self.tasks[task_id]
        updated = replace(task, state="cancelled", state_reason=reason)
        self.tasks[task_id] = updated
        self.cancelled.append((task_id, reason))
        return updated


class _Engineering:
    def __init__(self, queue):
        self.queue = queue


class _Store:
    def __init__(self, records):
        self.records = list(records)

    def list_active(self):
        return list(self.records)

    def get(self, task_id):
        return next((record for record in self.records if record.task_id == task_id), None)

    def transition(self, task_id, stage, *, worker, feedback=None, **_kwargs):
        current = self.get(task_id)
        assert current is not None
        updated = replace(current, stage=stage, last_feedback=feedback)
        self.records = [updated if record.task_id == task_id else record for record in self.records]
        return updated


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


def _coordinator(records, tasks=()):
    coordinator = object.__new__(GoalDirectedPipelineCoordinator)
    coordinator.store = _Store(records)
    coordinator.engineering = _Engineering(_Queue(tasks))
    coordinator.learning = _Worker("pipeline_learning_completed")
    coordinator.review = _Worker("pipeline_internal_review_approved")
    coordinator.development = _Worker("pipeline_development_completed")
    coordinator.repair = _Worker("pipeline_repair_completed")
    coordinator.triage = _Worker("pipeline_triaged")
    coordinator.validation = _Worker("pipeline_wait_validation")
    coordinator._recover_orphan_review = lambda: None
    return coordinator


def _stale_release_task(task_id="stale-release"):
    return _Task(
        task_id=task_id,
        state="failed",
        payload={
            "source": "genesis.evolution_learning",
            "discovery": {
                "finding": {
                    "new_capability": True,
                    "fallback_from": "no_existing_capability_domain",
                    "capability_domains": ["emerging_capability"],
                }
            },
            "learning": {
                "source": "github:ggml-org/llama.cpp",
                "title": "b10590",
                "summary": (
                    "<details open> vendor : update subprocess.h (#27409) </details> "
                    "**Website:** - <https://llama.app> **Attestations:** release artifacts"
                ),
                "url": "https://github.com/ggml-org/llama.cpp/releases/tag/b10590",
            },
        },
    )


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


def test_existing_durable_review_preempts_unrelated_preferred_goal():
    durable = _Record(
        "durable-review",
        "review_ready",
        candidate_sha="a" * 40,
        review_ref="genesis/review-aaaaaaaaaaaa",
        updated_at="2026-08-22T00:00:00+00:00",
    )
    coordinator = _coordinator(
        [
            _Record("repair-a", "needs_repair"),
            durable,
        ]
    )

    result = coordinator.run_once(preferred_task_id="repair-a")

    assert result["handled"] is True
    assert result["action"] == "pipeline_internal_review_approved"
    assert result["goal_directed"] is False
    assert result["preferred_task_id"] == "repair-a"
    assert result["durable_review_resumed"] == {
        "task_id": "durable-review",
        "candidate_sha": "a" * 40,
        "review_ref": "genesis/review-aaaaaaaaaaaa",
    }
    assert coordinator.review.seen == ["durable-review"]
    assert coordinator.repair.seen == []


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


def test_stale_unknown_release_fragment_is_retired_before_development():
    task = _stale_release_task()
    coordinator = _coordinator(
        [_Record(task.task_id, "needs_development_revision")],
        [task],
    )

    result = coordinator.run_once(preferred_task_id=task.task_id)

    assert result["handled"] is True
    assert result["action"] == "pipeline_learning_task_retired"
    assert result["retirement_reason"] == "release_fragment_not_transferable_policy"
    assert result["preferred_task_id"] == task.task_id
    assert result["goal_directed"] is False
    assert coordinator.engineering.queue.get(task.task_id).state == "cancelled"
    assert coordinator.store.get(task.task_id).stage == "quarantined"
    assert coordinator.development.seen == []


def test_arxiv_unknown_domain_is_not_retired_by_release_policy():
    task = _stale_release_task("paper-task")
    task = replace(
        task,
        state="assigned",
        payload={
            **task.payload,
            "learning": {
                "source": "arxiv",
                "title": "Adaptive endpoint bracketing",
                "summary": (
                    "Adaptive endpoint bracketing evaluates only candidates that can still affect the physical report "
                    "and otherwise safely coarsens or abstains."
                ),
                "url": "https://arxiv.org/abs/2608.12345",
            },
        },
    )
    coordinator = _coordinator([_Record(task.task_id, "development_ready")], [task])

    result = coordinator.run_once(preferred_task_id=task.task_id)

    assert result["action"] == "pipeline_development_completed"
    assert result["goal_directed"] is True
    assert coordinator.development.seen == [task.task_id]
    assert coordinator.engineering.queue.cancelled == []


def test_known_capability_release_is_not_retired_by_release_policy():
    task = _stale_release_task("known-release")
    finding = {
        **task.payload["discovery"]["finding"],
        "capability_domains": ["model_runtime"],
    }
    task = replace(
        task,
        state="assigned",
        payload={
            **task.payload,
            "discovery": {"finding": finding},
            "learning": {
                "source": "github:huggingface/transformers",
                "title": "v5.15.1",
                "summary": (
                    "Transformer inference fixes token device mismatch during decoding and tensor placement (#47877). "
                    "The runtime keeps candidate tokens aligned with the selected inference device."
                ),
                "url": "https://github.com/huggingface/transformers/releases/tag/v5.15.1",
            },
        },
    )
    coordinator = _coordinator([_Record(task.task_id, "development_ready")], [task])

    result = coordinator.run_once(preferred_task_id=task.task_id)

    assert result["action"] == "pipeline_development_completed"
    assert result["goal_directed"] is True
    assert coordinator.development.seen == [task.task_id]
    assert coordinator.engineering.queue.cancelled == []


def test_review_ready_stale_release_is_not_retired_by_predevelopment_gate():
    task = _stale_release_task("review-task")
    coordinator = _coordinator(
        [
            _Record(
                task.task_id,
                "review_ready",
                candidate_sha="b" * 40,
                review_ref="genesis/review-bbbbbbbbbbbb",
            )
        ],
        [task],
    )

    result = coordinator.run_once(preferred_task_id=task.task_id)

    assert result["action"] == "pipeline_internal_review_approved"
    assert coordinator.review.seen == [task.task_id]
    assert coordinator.engineering.queue.cancelled == []


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