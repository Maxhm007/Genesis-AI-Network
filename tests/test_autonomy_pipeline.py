from __future__ import annotations

from pathlib import Path

from genesis.autonomy_pipeline import PipelineStore, ReviewWorker, TriageWorker
from genesis.modules.registry import ModuleRegistry
from genesis.modules.task_queue import PersistentTaskQueue
from genesis.pulse import GenePulse


class _EngineeringStub:
    def __init__(self, queue: PersistentTaskQueue) -> None:
        self.queue = queue


def _discovery(target: str, confidence: float = 0.9) -> dict:
    return {
        "status": "issue_enqueued",
        "target": target,
        "finding": {
            "target": target,
            "decision": "issue",
            "summary": "Concrete testable defect",
            "acceptance": "Expected behavior is preserved",
            "confidence_normalized": confidence,
        },
    }


def test_pipeline_uses_same_sqlite_queue_and_triages_to_repair(tmp_path: Path) -> None:
    target = tmp_path / "genesis" / "example.py"
    target.parent.mkdir(parents=True)
    target.write_text("def value():\n    return 1\n", encoding="utf-8")
    queue = PersistentTaskQueue(tmp_path / "runtime" / "genesis_tasks.sqlite3")
    task = queue.create(
        "Repair discovered example issue",
        module_id="genesis.coding",
        payload={"source": "genesis.issue_discovery"},
    )
    store = PipelineStore(queue.path)
    record = store.register_discovery(task.task_id, "genesis/example.py", _discovery("genesis/example.py"))

    result = TriageWorker(tmp_path, _EngineeringStub(queue), store).run(record)

    assert result["action"] == "pipeline_triaged"
    assert queue.get(task.task_id).state == "assigned"
    assert store.get(task.task_id).stage == "repair_ready"
    assert store.path == queue.path


def test_triage_quarantines_protected_control_plane_target(tmp_path: Path) -> None:
    target = tmp_path / "genesis" / "security.py"
    target.parent.mkdir(parents=True)
    target.write_text("def protected():\n    return True\n", encoding="utf-8")
    queue = PersistentTaskQueue(tmp_path / "runtime" / "genesis_tasks.sqlite3")
    task = queue.create(
        "Do not autonomously alter security",
        module_id="genesis.coding",
        payload={"source": "genesis.issue_discovery"},
    )
    store = PipelineStore(queue.path)
    record = store.register_discovery(task.task_id, "genesis/security.py", _discovery("genesis/security.py"))

    result = TriageWorker(tmp_path, _EngineeringStub(queue), store).run(record)

    assert result["action"] == "pipeline_quarantined"
    assert store.get(task.task_id).stage == "quarantined"
    assert queue.get(task.task_id).state == "new"


def test_internal_review_feedback_returns_same_task_to_repair_queue(tmp_path: Path) -> None:
    queue = PersistentTaskQueue(tmp_path / "runtime" / "genesis_tasks.sqlite3")
    task = queue.create(
        "Repair a discovered issue",
        module_id="genesis.coding",
        payload={"source": "genesis.issue_discovery"},
        max_attempts=4,
    )
    queue.transition(task.task_id, "assigned", module_id="genesis.coding")
    queue.transition(task.task_id, "running", module_id="genesis.coding")
    queue.transition(task.task_id, "review", module_id="genesis.coding")
    store = PipelineStore(queue.path)
    record = store.register_discovery(task.task_id, "genesis/example.py", _discovery("genesis/example.py"))
    record = store.transition(
        record.task_id,
        "review_ready",
        worker="repair",
        candidate_branch="genesis/candidate-example",
        candidate_sha="deadbeef",
        review_ref="genesis/review-deadbeef",
    )

    result = ReviewWorker(tmp_path, _EngineeringStub(queue), store)._send_back(record, "review found regression")

    assert result["action"] == "pipeline_internal_review_needs_repair"
    assert queue.get(task.task_id).state == "failed"
    assert queue.get(task.task_id).task_id == task.task_id
    assert store.get(task.task_id).stage == "needs_repair"
    assert "review found regression" in (store.get(task.task_id).last_feedback or "")


def test_pipeline_pulse_chains_only_executable_stages() -> None:
    assert GenePulse._next_pulse_decision("pipeline_issue_discovered", {})[0] is True
    assert GenePulse._next_pulse_decision("pipeline_triaged", {})[0] is True
    assert GenePulse._next_pulse_decision("pipeline_repair_completed", {})[0] is True
    assert GenePulse._next_pulse_decision("pipeline_internal_review_needs_repair", {})[0] is True
    assert GenePulse._next_pulse_decision("pipeline_internal_review_approved", {})[0] is False
    assert GenePulse._next_pulse_decision("pipeline_wait_validation", {})[0] is False
    assert GenePulse._next_pulse_decision("pipeline_promotion_observed", {})[0] is True
    assert GenePulse._next_pulse_decision("pipeline_learning_completed", {})[0] is True


def test_autonomy_pipeline_is_registered_without_main_or_validation_authority(tmp_path: Path) -> None:
    # Use repository config directly; this test runs from the repository root.
    root = Path(__file__).resolve().parents[1]
    registry = ModuleRegistry.from_default_config(root)
    module = registry.get("genesis.autonomy_pipeline")
    assert module is not None
    assert module.metadata["direct_main_write"] is False
    assert module.metadata["validation_authority"] is False
    assert module.metadata["protected_file_bypass"] is False
    assert module.metadata["internal_review_required_before_candidate_publication"] is True


def test_gene_pulse_workflow_has_review_ref_before_candidate_ref() -> None:
    root = Path(__file__).resolve().parents[1]
    workflow = (root / ".github" / "workflows" / "gene-pulse.yml").read_text(encoding="utf-8")
    review_step = workflow.index("Push isolated candidate to review queue")
    candidate_step = workflow.index("Publish internally reviewed exact candidate")
    assert review_step < candidate_step
    assert "genesis/review-*" in workflow
    assert "pipeline_internal_review_approved" in workflow
