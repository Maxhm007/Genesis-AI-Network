from __future__ import annotations

from dataclasses import dataclass, field

from genesis.goal_orchestrator import GoalOrchestrator


@dataclass(frozen=True)
class _Record:
    task_id: str
    stage: str
    target_path: str = "genesis/example.py"
    discovery: dict = field(default_factory=dict)
    updated_at: str = "2026-08-22T00:00:00+00:00"


class _Store:
    def __init__(self, records):
        self.records = {record.task_id: record for record in records}

    def list_active(self):
        return [
            record
            for record in self.records.values()
            if record.stage not in {"closed", "quarantined"}
        ]

    def get(self, task_id):
        return self.records.get(task_id)


class _Pipeline:
    def __init__(self, records):
        self.store = _Store(records)


def _steps(goal):
    return {step["step_id"]: step for step in goal["steps"]}


def test_idle_state_creates_dependency_graph_and_selects_discovery(tmp_path):
    orchestrator = GoalOrchestrator(tmp_path, "gene-test")

    state = orchestrator.sync(_Pipeline([]))

    selected = state["selected"]
    assert selected["goal"]["goal_id"] == "genesis:self-improvement"
    assert selected["subtask"]["step_id"] == "discover"
    assert selected["subtask"]["specialist"] == "discovery"
    assert selected["subtask"]["dependencies"] == []


def test_pipeline_goal_decomposes_and_selects_repair_after_triage(tmp_path):
    record = _Record("repair-me", "needs_repair", "genesis/broken.py")
    orchestrator = GoalOrchestrator(tmp_path, "gene-test")

    state = orchestrator.sync(_Pipeline([record]))
    selected = state["selected"]
    goal = orchestrator.state["goals"]["pipeline:repair-me"]
    steps = _steps(goal)

    assert selected["goal"]["goal_id"] == "pipeline:repair-me"
    assert selected["subtask"]["step_id"] == "execute"
    assert selected["subtask"]["specialist"] == "repair"
    assert selected["subtask"]["action"] == "repair_issue"
    assert steps["discover"]["status"] == "complete"
    assert steps["triage"]["status"] == "complete"
    assert steps["execute"]["status"] == "ready"
    assert steps["review"]["status"] == "pending"


def test_development_goal_assigns_development_specialist(tmp_path):
    record = _Record(
        "develop-me",
        "development_ready",
        "genesis/new_capability.py",
        discovery={"source": "genesis.evolution_learning"},
    )
    orchestrator = GoalOrchestrator(tmp_path, "gene-test")

    selected = orchestrator.sync(_Pipeline([record]))["selected"]

    assert selected["goal"]["goal_id"] == "pipeline:develop-me"
    assert selected["subtask"]["specialist"] == "development"
    assert selected["subtask"]["action"] == "develop_capability"


def test_failure_replans_same_goal_and_persists_attempt(tmp_path):
    record = _Record("repair-me", "needs_repair")
    pipeline = _Pipeline([record])
    orchestrator = GoalOrchestrator(tmp_path, "gene-test")
    orchestrator.sync(pipeline)

    observed = orchestrator.observe(
        {
            "action": "pipeline_repair_retry",
            "decision": {"task_id": "repair-me"},
            "pipeline": {"record": {"task_id": "repair-me", "stage": "needs_repair"}},
        }
    )

    goal = orchestrator.state["goals"]["pipeline:repair-me"]
    assert _steps(goal)["execute"]["attempts"] == 1
    assert _steps(goal)["execute"]["status"] == "ready"
    assert goal["replans"] == 1
    assert observed["metrics"]["replans"] == 1

    reloaded = GoalOrchestrator(tmp_path, "gene-test")
    reloaded_goal = reloaded.state["goals"]["pipeline:repair-me"]
    assert _steps(reloaded_goal)["execute"]["attempts"] == 1
    assert reloaded_goal["replans"] == 1


def test_review_success_unlocks_validation_dependency(tmp_path):
    record = _Record("review-me", "review_ready")
    orchestrator = GoalOrchestrator(tmp_path, "gene-test")
    orchestrator.sync(_Pipeline([record]))

    orchestrator.observe(
        {
            "action": "pipeline_internal_review_approved",
            "decision": {"task_id": "review-me"},
            "pipeline": {"record": {"task_id": "review-me", "stage": "validation_ready"}},
        }
    )

    goal = orchestrator.state["goals"]["pipeline:review-me"]
    steps = _steps(goal)
    assert steps["review"]["status"] == "complete"
    assert steps["validate"]["status"] == "ready"
    assert orchestrator.select_next()["subtask"]["step_id"] == "validate"


def test_executable_review_goal_outranks_validation_wait_goal(tmp_path):
    pipeline = _Pipeline(
        [
            _Record("validate-me", "validation_ready", "genesis/old.py"),
            _Record("review-me", "review_ready", "genesis/new.py"),
        ]
    )
    orchestrator = GoalOrchestrator(tmp_path, "gene-test")

    selected = orchestrator.sync(pipeline)["selected"]

    assert selected["goal"]["goal_id"] == "pipeline:review-me"
    assert selected["subtask"]["step_id"] == "review"
