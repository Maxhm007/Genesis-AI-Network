from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from genesis.goal_orchestrator import GoalOrchestrator
from genesis.modules.task_queue import PersistentTaskQueue
from genesis.provider_fallback import (
    LEARNED_CAPABILITY_MARKER,
    LEARNED_CAPABILITY_TARGET,
    _normalize_learned_capability_proposal,
)


@dataclass(frozen=True)
class _Record:
    task_id: str
    stage: str
    target_path: str
    discovery: dict = field(default_factory=dict)
    updated_at: str = "2026-08-24T00:00:00+00:00"


class _Store:
    def __init__(self, records):
        self.records = {record.task_id: record for record in records}

    def list_active(self):
        return list(self.records.values())

    def get(self, task_id):
        return self.records.get(task_id)


class _Pipeline:
    def __init__(self, records):
        self.store = _Store(records)


def _queue(tmp_path: Path) -> PersistentTaskQueue:
    return PersistentTaskQueue(tmp_path / "runtime" / "genesis_tasks.sqlite3")


def test_goal_scheduler_prefers_measured_growth_over_speculative_learning(tmp_path: Path) -> None:
    queue = _queue(tmp_path)
    speculative = queue.create(
        "Speculative learned capability",
        module_id="genesis.coding",
        priority=100,
        payload={"task_type": "new_capability", "target_path": LEARNED_CAPABILITY_TARGET},
    )
    growth = queue.create(
        "Improve measured SWE-Bench deficit",
        module_id="genesis.improvement",
        priority=95,
        payload={"task_type": "capability_growth", "target_path": "genesis/coding.py"},
    )
    records = [
        _Record(speculative.task_id, "needs_development_revision", LEARNED_CAPABILITY_TARGET),
        _Record(growth.task_id, "needs_development_revision", "genesis/coding.py"),
    ]

    selected = GoalOrchestrator(tmp_path, "gene-test").sync(_Pipeline(records))["selected"]

    assert selected["goal"]["task_id"] == growth.task_id
    assert selected["goal"]["priority"] == 94


def test_durable_review_still_outranks_measured_growth(tmp_path: Path) -> None:
    queue = _queue(tmp_path)
    review = queue.create(
        "Finish existing candidate review",
        module_id="genesis.coding",
        priority=1,
        payload={"task_type": "repair"},
    )
    growth = queue.create(
        "Improve measured SWE-Bench deficit",
        module_id="genesis.improvement",
        priority=95,
        payload={"task_type": "capability_growth", "target_path": "genesis/coding.py"},
    )
    records = [
        _Record(review.task_id, "review_ready", "genesis/repair.py"),
        _Record(growth.task_id, "needs_development_revision", "genesis/coding.py"),
    ]

    selected = GoalOrchestrator(tmp_path, "gene-test").sync(_Pipeline(records))["selected"]

    assert selected["goal"]["task_id"] == review.task_id
    assert selected["goal"]["priority"] == 95


def test_scoped_marker_repair_preserves_marker_for_compact_insertion() -> None:
    current = "value = 1\n\n" + LEARNED_CAPABILITY_MARKER
    proposal = {
        "edits": [
            {
                "path": LEARNED_CAPABILITY_TARGET,
                "start_line": 3,
                "end_line": 3,
                "new": "def learned_value():\n    return 2",
            }
        ]
    }

    normalized = _normalize_learned_capability_proposal(proposal, current)
    replacement = normalized["edits"][0]["new"]

    assert replacement.count(LEARNED_CAPABILITY_MARKER) == 1
    assert replacement.endswith(LEARNED_CAPABILITY_MARKER)
    assert "def learned_value" in replacement


def test_scoped_marker_repair_preserves_marker_for_append_only_full_file() -> None:
    current = "value = 1\n\n" + LEARNED_CAPABILITY_MARKER
    proposal = {
        "files": {
            LEARNED_CAPABILITY_TARGET: "value = 1\n\ndef learned_value():\n    return 2\n"
        }
    }

    normalized = _normalize_learned_capability_proposal(proposal, current)
    proposed = normalized["files"][LEARNED_CAPABILITY_TARGET]

    assert proposed.count(LEARNED_CAPABILITY_MARKER) == 1
    assert proposed.startswith("value = 1\n\n")
    assert proposed.endswith(LEARNED_CAPABILITY_MARKER)


def test_scoped_marker_repair_does_not_widen_unrelated_edit() -> None:
    current = "value = 1\n\n" + LEARNED_CAPABILITY_MARKER
    proposal = {
        "edits": [
            {
                "path": LEARNED_CAPABILITY_TARGET,
                "start_line": 1,
                "end_line": 1,
                "new": "value = 2",
            }
        ]
    }

    normalized = _normalize_learned_capability_proposal(proposal, current)

    assert normalized == proposal
