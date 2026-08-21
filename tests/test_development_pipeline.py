from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from genesis.autonomy_pipeline import PipelineStore, ReviewWorker, TriageWorker
from genesis.bounded_autonomy_pipeline import (
    BoundedAutonomyPipelineCoordinator,
    SingleAttemptDevelopmentWorker,
    SingleAttemptRepairWorker,
)
from genesis.modules.task_queue import PersistentTaskQueue
from genesis.pulse import GenePulse


class _EngineeringStub:
    def __init__(self, queue: PersistentTaskQueue) -> None:
        self.queue = queue


def _learning_discovery(target: str) -> dict:
    return {
        "status": "upgrade_enqueued",
        "source": "genesis.evolution_learning",
        "target": target,
        "finding": {
            "target_path": target,
            "decision": "upgrade",
            "summary": "Add one bounded learned capability",
            "acceptance": "The new capability passes the full repository suite",
            "confidence_normalized": 0.9,
            "grounded": True,
            "new_capability": True,
        },
    }


def _learning_task(queue: PersistentTaskQueue, target: str):
    return queue.create(
        "Implement one grounded learned capability",
        module_id="genesis.coding",
        payload={
            "source": "genesis.evolution_learning",
            "task_type": "self_upgrade",
            "target_path": target,
        },
        max_attempts=4,
    )


def test_learning_upgrade_triages_to_development_not_repair(tmp_path: Path) -> None:
    target = tmp_path / "genesis" / "learned_capabilities.py"
    target.parent.mkdir(parents=True)
    target.write_text("# GENESIS_LEARNED_CAPABILITY_INSERTION_POINT\n", encoding="utf-8")
    queue = PersistentTaskQueue(tmp_path / "runtime" / "genesis_tasks.sqlite3")
    task = _learning_task(queue, "genesis/learned_capabilities.py")
    store = PipelineStore(queue.path)
    record = store.register_discovery(
        task.task_id,
        "genesis/learned_capabilities.py",
        _learning_discovery("genesis/learned_capabilities.py"),
    )

    result = TriageWorker(tmp_path, _EngineeringStub(queue), store).run(record)

    updated = store.get(task.task_id)
    assert result["action"] == "pipeline_development_triaged"
    assert queue.get(task.task_id).state == "assigned"
    assert updated is not None
    assert updated.stage == "development_ready"
    assert updated.development_attempts == 0
    assert updated.repair_attempts == 0


def test_internal_review_returns_learning_candidate_to_development(tmp_path: Path) -> None:
    queue = PersistentTaskQueue(tmp_path / "runtime" / "genesis_tasks.sqlite3")
    task = _learning_task(queue, "genesis/learned_capabilities.py")
    queue.transition(task.task_id, "assigned", module_id="genesis.coding")
    queue.transition(task.task_id, "running", module_id="genesis.coding")
    queue.transition(task.task_id, "review", module_id="genesis.coding")
    store = PipelineStore(queue.path)
    record = store.register_discovery(
        task.task_id,
        "genesis/learned_capabilities.py",
        _learning_discovery("genesis/learned_capabilities.py"),
    )
    record = store.transition(
        record.task_id,
        "review_ready",
        worker="development",
        candidate_branch="genesis/candidate-learning",
        candidate_sha="deadbeef",
        review_ref="genesis/review-deadbeef",
    )

    result = ReviewWorker(tmp_path, _EngineeringStub(queue), store)._send_back(
        record, "review found a regression"
    )

    updated = store.get(task.task_id)
    assert result["action"] == "pipeline_internal_review_needs_development"
    assert queue.get(task.task_id).state == "failed"
    assert updated is not None
    assert updated.stage == "needs_development_revision"
    assert updated.repair_attempts == 0
    assert "review found a regression" in (updated.last_feedback or "")


def test_pipeline_store_migrates_legacy_learning_repair_stage(tmp_path: Path) -> None:
    path = tmp_path / "runtime" / "genesis_tasks.sqlite3"
    path.parent.mkdir(parents=True)
    discovery = _learning_discovery("genesis/learned_capabilities.py")
    with sqlite3.connect(path) as db:
        db.execute(
            """
            CREATE TABLE genesis_autonomy_pipeline (
                task_id TEXT PRIMARY KEY,
                stage TEXT NOT NULL,
                target_path TEXT NOT NULL,
                candidate_branch TEXT,
                candidate_sha TEXT,
                review_ref TEXT,
                repair_attempts INTEGER NOT NULL DEFAULT 0,
                review_attempts INTEGER NOT NULL DEFAULT 0,
                last_feedback TEXT,
                discovery_json TEXT NOT NULL DEFAULT '{}',
                history_json TEXT NOT NULL DEFAULT '[]',
                updated_at TEXT NOT NULL
            )
            """
        )
        db.execute(
            """
            INSERT INTO genesis_autonomy_pipeline(
                task_id, stage, target_path, repair_attempts, discovery_json, updated_at
            ) VALUES(?, 'needs_repair', ?, 2, ?, ?)
            """,
            (
                "learning-task",
                "genesis/learned_capabilities.py",
                json.dumps(discovery, sort_keys=True),
                "2026-08-21T20:00:00+00:00",
            ),
        )

    record = PipelineStore(path).get("learning-task")

    assert record is not None
    assert record.stage == "needs_development_revision"
    assert record.development_attempts == 2
    assert record.repair_attempts == 0


def test_bounded_pipeline_has_distinct_development_and_repair_workers(tmp_path: Path) -> None:
    coordinator = BoundedAutonomyPipelineCoordinator(tmp_path)

    assert isinstance(coordinator.development, SingleAttemptDevelopmentWorker)
    assert isinstance(coordinator.repair, SingleAttemptRepairWorker)
    assert coordinator.development is not coordinator.repair


def test_development_actions_chain_without_becoming_repair_actions() -> None:
    assert GenePulse._next_pulse_decision("pipeline_development_triaged", {})[0] is True
    assert GenePulse._next_pulse_decision("pipeline_development_completed", {})[0] is True
    assert GenePulse._next_pulse_decision("pipeline_development_retry", {})[0] is True
    assert GenePulse._next_pulse_decision("pipeline_internal_review_needs_development", {})[0] is True
    assert GenePulse._next_pulse_decision("pipeline_wait_development_provider", {})[0] is False


def test_gene_pulse_publishes_development_candidates_through_same_review_gate() -> None:
    root = Path(__file__).resolve().parents[1]
    workflow = (root / ".github" / "workflows" / "gene-pulse.yml").read_text(encoding="utf-8")

    assert "pipeline_development_completed" in workflow
    assert "pipeline_internal_review_needs_development" in workflow
    assert "Push isolated candidate to review queue" in workflow
    assert "Publish internally reviewed exact candidate" in workflow
