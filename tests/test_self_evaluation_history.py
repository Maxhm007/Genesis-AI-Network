from pathlib import Path

from genesis.autonomy_proof import AutonomyProofLedger
from genesis.modules.task_queue import PersistentTaskQueue
from genesis.self_evaluation import GenesisSelfEvaluation
from scripts.self_evaluation_dashboard import (
    AUTO_BODY_MARKER,
    PROOF_MARKER,
    has_autonomous_provenance,
    improvement_from_pr,
    merged_self_development_prs,
)


def complete_engineering_task(tmp_path: Path, objective: str = "Improve autonomous task selection") -> None:
    queue = PersistentTaskQueue(tmp_path / "runtime" / "genesis_tasks.sqlite3")
    task = queue.create(objective, module_id="genesis.coding", priority=80)
    queue.transition(task.task_id, "assigned")
    queue.transition(task.task_id, "running")
    queue.transition(task.task_id, "review")
    queue.transition(task.task_id, "complete")


def test_completed_task_without_autonomy_proof_gets_no_self_development_credit(tmp_path: Path) -> None:
    complete_engineering_task(tmp_path)
    report = GenesisSelfEvaluation(tmp_path).report()
    assert report["completed_self_development_tasks"] == 0
    assert report["completed_engineering_tasks_observed"] == 1
    assert report["recent_completed_tasks"][0]["improved"] == "Improve autonomous task selection"
    assert report["recent_completed_tasks"][0]["credit"] == "engineering_memory_only"
    assert report["recent_autonomous_improvements"] == []


def test_genesis_autonomous_cycle_gets_self_development_credit(tmp_path: Path) -> None:
    complete_engineering_task(tmp_path)
    ledger = AutonomyProofLedger(tmp_path)
    ledger.record(
        cycle_id="cycle-1",
        stage="discovery",
        actor="genesis.coding",
        outcome="started",
        details={"title": "Improve autonomous task selection", "files": ["genesis/selector.py"]},
    )
    ledger.record(
        cycle_id="cycle-1",
        stage="candidate_created",
        actor="genesis.coding",
        outcome="success",
        details={"branch": "genesis/candidate-cycle-1", "commit_sha": "abc123"},
    )
    ledger.record(cycle_id="cycle-1", stage="cycle_complete", actor="genesis.coding", outcome="success")

    report = GenesisSelfEvaluation(tmp_path).report()
    assert report["completed_self_development_tasks"] == 1
    assert report["recent_autonomous_improvements"][0]["classification"] == "genesis_autonomous"
    assert report["recent_autonomous_improvements"][0]["improved"] == "Improve autonomous task selection"


def test_dashboard_excludes_manual_or_assistant_candidate_prs() -> None:
    pulls = [
        {
            "number": 82,
            "title": "Show completed self-development and exact improvements",
            "body": "## Goal\nAssistant-created improvement.\n",
            "merged_at": "2026-08-19T03:50:00Z",
            "html_url": "https://example.test/82",
            "head": {"ref": "genesis/candidate-self-evaluation-history"},
        },
        {
            "number": 81,
            "title": "Add safeguarded parallel autonomous development",
            "body": "## Goal\nAssistant-created privileged improvement.\n",
            "merged_at": "2026-08-19T03:26:00Z",
            "html_url": "https://example.test/81",
            "head": {"ref": "genesis/privileged-candidate-parallel-development"},
        },
    ]
    assert merged_self_development_prs(pulls) == []


def test_dashboard_counts_auto_opened_genesis_candidate() -> None:
    pr = {
        "number": 90,
        "title": "Genesis autonomous candidate: genesis/candidate-cycle-90",
        "body": AUTO_BODY_MARKER + ".",
        "merged_at": "2026-08-19T05:00:00Z",
        "html_url": "https://example.test/90",
        "head": {"ref": "genesis/candidate-cycle-90"},
    }
    history = merged_self_development_prs([pr])
    assert len(history) == 1
    assert history[0]["classification"] == "genesis_autonomous"


def test_privileged_candidate_requires_explicit_autonomy_proof_marker() -> None:
    pr = {
        "number": 91,
        "title": "Privileged autonomous improvement",
        "body": f"{PROOF_MARKER}\n## Goal\nImprove guarded orchestration.",
        "merged_at": "2026-08-19T05:10:00Z",
        "head": {"ref": "genesis/privileged-candidate-guarded-orchestration"},
    }
    assert has_autonomous_provenance(pr) is True
    history = merged_self_development_prs([pr])
    assert history[0]["lane"] == "privileged"


def test_improvement_prefers_goal_section() -> None:
    pr = {"title": "Fallback title", "body": "## Goal\nMake failures less repetitive.\n\n## Changes\nAdd cooldown."}
    assert improvement_from_pr(pr) == "Make failures less repetitive."
