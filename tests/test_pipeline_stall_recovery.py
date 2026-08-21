from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from genesis.autonomy_pipeline import PipelineStore
from genesis.bounded_autonomy_pipeline import (
    BoundedAutonomyPipelineCoordinator,
    ResumableDiscoveryWorker,
    SingleAttemptRepairWorker,
)
from genesis.modules.task_queue import PersistentTaskQueue
from genesis.pulse import GenePulse


class NoIssueProvider:
    name = "test-provider"

    def __init__(self) -> None:
        self.prompts: list[str] = []

    def available(self) -> bool:
        return True

    def reason(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return json.dumps(
            {
                "decision": "no_issue",
                "summary": "No confirmed defect in this batch item.",
                "acceptance": "",
                "confidence": "medium",
            }
        )


class FakeCoding:
    def __init__(self, provider) -> None:
        self.provider = provider

    def _provider(self):
        return self.provider


class DiscoveryEngineering:
    def __init__(self, root: Path, provider) -> None:
        self.queue = PersistentTaskQueue(root / "runtime" / "genesis_tasks.sqlite3")
        self.coding = FakeCoding(provider)


class RepairEngineering:
    MAX_CANDIDATE_REVISIONS = 2

    def __init__(self, root: Path) -> None:
        self.queue = PersistentTaskQueue(root / "runtime" / "genesis_tasks.sqlite3")
        self.objectives: list[str] = []
        self.revision_budgets: list[int] = []

    def _attempt_task(self, task, runtime: Path) -> dict:
        self.objectives.append(task.objective)
        self.revision_budgets.append(self.MAX_CANDIDATE_REVISIONS)
        return {
            "coding_status": "candidate_not_committed",
            "candidate": {
                "committed": False,
                "tests_passed": False,
                "message": "FAILED tests/test_worker.py::test_boundary",
            },
            "candidate_security": None,
        }


class ScopeViolationEngineering(RepairEngineering):
    def _attempt_task(self, task, runtime: Path) -> dict:
        self.objectives.append(task.objective)
        self.revision_budgets.append(self.MAX_CANDIDATE_REVISIONS)
        current = self.queue.get(task.task_id)
        assert current is not None
        if current.state != "running":
            if current.state != "assigned":
                current = self.queue.transition(task.task_id, "assigned", module_id="genesis.coding")
            current = self.queue.transition(task.task_id, "running", module_id="genesis.coding")
        self.queue.transition(task.task_id, "review", module_id="genesis.coding")
        return {
            "coding_status": "candidate_created",
            "candidate": {
                "committed": True,
                "tests_passed": True,
                "message": "candidate committed",
                "commit_sha": "abc123",
                "branch": "genesis/candidate-scope-test",
                "changed_files": ("genesis/worker.py", "tests/test_worker.py"),
            },
            "candidate_security": {"status": "pass"},
        }


class CoordinatorEngineering(DiscoveryEngineering):
    pass


def _write(root: Path, relative: str, content: str) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_discovery_advances_across_resumable_batches(tmp_path: Path) -> None:
    for index in range(7):
        _write(tmp_path, f"genesis/module_{index}.py", f"def value_{index}(x):\n    return x\n")
    provider = NoIssueProvider()
    engineering = DiscoveryEngineering(tmp_path, provider)
    store = PipelineStore(engineering.queue.path)
    worker = ResumableDiscoveryWorker(tmp_path, engineering, store)

    first = worker.run()
    second = worker.run()

    first_targets = [item["target"] for item in first["scanned"]]
    second_targets = [item["target"] for item in second["scanned"]]
    assert first["batch_offset"] == 0
    assert first["batch_size"] == 3
    assert second["batch_offset"] == 3
    assert first_targets
    assert second_targets
    assert set(first_targets).isdisjoint(second_targets)
    assert second["next_batch_offset"] == 6


def test_repair_yields_after_one_candidate_attempt_and_reuses_feedback(tmp_path: Path) -> None:
    _write(tmp_path, "genesis/worker.py", "def worker(value):\n    return value\n")
    engineering = RepairEngineering(tmp_path)
    store = PipelineStore(engineering.queue.path)
    task = engineering.queue.create(
        "Repair the worker boundary.",
        module_id="genesis.coding",
        payload={"source": "genesis.issue_discovery", "target_path": "genesis/worker.py"},
        max_attempts=4,
    )
    engineering.queue.transition(task.task_id, "assigned", module_id="genesis.coding")
    store.register_discovery(
        task.task_id,
        "genesis/worker.py",
        {"finding": {"confidence_normalized": 0.9}},
    )
    store.transition(task.task_id, "repair_ready", worker="triage")
    worker = SingleAttemptRepairWorker(tmp_path, engineering, store)

    first = worker.run(store.get(task.task_id))
    second = worker.run(store.get(task.task_id))

    assert first["action"] == "pipeline_repair_retry"
    assert second["action"] == "pipeline_repair_retry"
    assert engineering.revision_budgets == [0, 0]
    assert engineering.MAX_CANDIDATE_REVISIONS == 2
    assert "FAILED tests/test_worker.py::test_boundary" in engineering.objectives[1]
    assert store.get(task.task_id).repair_attempts == 2


def test_repair_rejects_candidate_that_changes_outside_discovered_target(tmp_path: Path) -> None:
    _write(tmp_path, "genesis/worker.py", "def worker(value):\n    return value\n")
    _write(tmp_path, "tests/test_worker.py", "def test_worker():\n    assert True\n")
    engineering = ScopeViolationEngineering(tmp_path)
    store = PipelineStore(engineering.queue.path)
    task = engineering.queue.create(
        "Repair only the discovered worker implementation.",
        module_id="genesis.coding",
        payload={"source": "genesis.issue_discovery", "target_path": "genesis/worker.py"},
        max_attempts=4,
    )
    engineering.queue.transition(task.task_id, "assigned", module_id="genesis.coding")
    store.register_discovery(
        task.task_id,
        "genesis/worker.py",
        {"finding": {"confidence_normalized": 0.9}},
    )
    store.transition(task.task_id, "repair_ready", worker="triage")

    result = SingleAttemptRepairWorker(tmp_path, engineering, store).run(store.get(task.task_id))

    assert result["action"] == "pipeline_repair_retry"
    assert result["attempt"]["coding_status"] == "candidate_rejected_by_scope"
    assert "repair_scope_violation" in result["attempt"]["error"]
    assert "tests/test_worker.py" in result["attempt"]["error"]
    assert "review_candidate" not in result
    assert engineering.queue.get(task.task_id).state == "failed"
    assert store.get(task.task_id).stage == "needs_repair"
    assert "repair_scope_violation" in (store.get(task.task_id).last_feedback or "")


def test_validation_wait_does_not_starve_discovered_work(tmp_path: Path) -> None:
    _write(tmp_path, "genesis/worker.py", "def worker(value):\n    return value\n")
    provider = NoIssueProvider()
    engineering = CoordinatorEngineering(tmp_path, provider)
    coordinator = BoundedAutonomyPipelineCoordinator(tmp_path, engineering)

    waiting = engineering.queue.create(
        "Waiting for independent validation.",
        module_id="genesis.coding",
        payload={"source": "genesis.issue_discovery", "target_path": "genesis/worker.py"},
    )
    coordinator.store.register_discovery(
        waiting.task_id,
        "genesis/worker.py",
        {"finding": {"confidence_normalized": 0.9}},
    )
    coordinator.store.transition(
        waiting.task_id,
        "validation_ready",
        worker="review",
        candidate_sha="abc123",
        candidate_branch="genesis/candidate-waiting",
    )

    discovered = engineering.queue.create(
        "Repair a newly discovered worker issue.",
        module_id="genesis.coding",
        payload={"source": "genesis.issue_discovery", "target_path": "genesis/worker.py"},
    )
    coordinator.store.register_discovery(
        discovered.task_id,
        "genesis/worker.py",
        {"finding": {"confidence_normalized": 0.9}},
    )

    class WaitingValidation:
        def run(self, record):
            return {"action": "pipeline_wait_validation", "record": asdict(record)}

    coordinator.validation = WaitingValidation()
    result = coordinator.run_once()

    assert result["action"] == "pipeline_triaged"
    assert result["record"]["task_id"] == discovered.task_id
    assert coordinator.store.get(waiting.task_id).stage == "validation_ready"


def test_discovery_continue_requests_next_pulse() -> None:
    needs_next, reason = GenePulse._next_pulse_decision("pipeline_discovery_continue", {})
    assert needs_next is True
    assert reason == "next_discovery_batch_ready"


def test_gene_pulse_runtime_and_stale_cleanup_are_bounded() -> None:
    root = Path(__file__).resolve().parents[1]
    pulse = (root / ".github" / "workflows" / "gene-pulse.yml").read_text(encoding="utf-8")
    control = (root / ".github" / "workflows" / "pulse-control.yml").read_text(encoding="utf-8")
    worker = (root / "scripts" / "gene_continuous_work.py").read_text(encoding="utf-8")

    assert "GENESIS_PROVIDER_TIMEOUT_SECONDS: '60'" in pulse
    assert "freshness_seconds=7200" in control
    assert "for workflow in gene-pulse.yml file-self-review.yml manual-self-repair.yml" in control
    assert "for status in queued in_progress" in control
    assert "gh run cancel" in control
    assert "/force-cancel" in control
    assert "stale_in_progress" in control
    assert "stale_cancel_failures" in control
    assert "${#fresh[@]} > 0 || ${#stale_in_progress[@]} > 0" in control
    assert "${#fresh[@]} > 0 || ${#stale_in_progress[@]} > 0 || ${#stale_cancel_failures[@]} > 0" not in control
    assert "if: steps.gate.outputs.busy == 'false'" in control
    assert "PULSE_DISCOVERY_SOURCE_BYTES = 5_000" in worker
    assert "PULSE_DISCOVERY_TEST_BYTES = 2_000" in worker
    assert "no_bounded_code_context_for_gene_pulse" in worker
