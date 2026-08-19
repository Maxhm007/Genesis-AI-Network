from pathlib import Path

from genesis.autonomy_proof import AutonomyProofLedger
from genesis.modules.task_queue import PersistentTaskQueue
from genesis.self_evaluation import GenesisSelfEvaluation
from scripts.self_evaluation_dashboard import (
    AUTO_BODY_MARKER,
    PROOF_MARKER,
    attributed_development_prs,
    classify_pr_attribution,
    has_autonomous_provenance,
    improvement_from_pr,
    merged_self_development_prs,
    summarize,
)


def complete_engineering_task(tmp_path: Path, objective: str = "Improve autonomous task selection") -> None:
    queue = PersistentTaskQueue(tmp_path / "runtime" / "genesis_tasks.sqlite3")
    task = queue.create(objective, module_id="genesis.coding", priority=80)
    queue.transition(task.task_id, "assigned")
    queue.transition(task.task_id, "running")
    queue.transition(task.task_id, "review")
    queue.transition(task.task_id, "complete")


def record_cycle(tmp_path: Path, cycle_id: str, actor: str, title: str) -> None:
    ledger = AutonomyProofLedger(tmp_path)
    ledger.record(
        cycle_id=cycle_id,
        stage="discovery",
        actor=actor,
        outcome="started",
        details={"title": title, "files": ["genesis/example.py"]},
    )
    ledger.record(
        cycle_id=cycle_id,
        stage="candidate_created",
        actor=actor,
        outcome="success",
        details={"branch": f"genesis/candidate-{cycle_id}", "commit_sha": cycle_id},
    )
    ledger.record(cycle_id=cycle_id, stage="cycle_complete", actor=actor, outcome="success")


def test_completed_task_without_autonomy_proof_gets_no_self_development_credit(tmp_path: Path) -> None:
    complete_engineering_task(tmp_path)
    report = GenesisSelfEvaluation(tmp_path).report()
    assert report["completed_self_development_tasks"] == 0
    assert report["completed_engineering_tasks_observed"] == 1
    assert report["recent_completed_tasks"][0]["credit"] == "engineering_memory_only"


def test_genesis_sees_three_way_attribution(tmp_path: Path) -> None:
    record_cycle(tmp_path, "auto", "genesis.coding", "Genesis improvement")
    record_cycle(tmp_path, "assist", "chatgpt", "Assisted improvement")
    record_cycle(tmp_path, "owner", "owner", "Owner improvement")

    report = GenesisSelfEvaluation(tmp_path).report()
    assert report["development_attribution"] == {
        "genesis_autonomous": 1,
        "assisted": 1,
        "owner": 1,
        "total_proven_cycles": 3,
    }
    assert report["completed_self_development_tasks"] == 1
    assert report["recent_autonomous_improvements"][0]["improved"] == "Genesis improvement"
    assert report["recent_assisted_improvements"][0]["improved"] == "Assisted improvement"
    assert report["recent_owner_improvements"][0]["improved"] == "Owner improvement"


def test_dashboard_classifies_autonomous_assisted_and_owner_once_each() -> None:
    pulls = [
        {
            "number": 90,
            "title": "Genesis autonomous candidate: genesis/candidate-cycle-90",
            "body": AUTO_BODY_MARKER + ".\n## Goal\nAutonomous improvement.",
            "merged_at": "2026-08-19T05:00:00Z",
            "html_url": "https://example.test/90",
            "head": {"ref": "genesis/candidate-cycle-90"},
        },
        {
            "number": 82,
            "title": "Assistant improvement",
            "body": "## Goal\nAssisted improvement.\n\n## Attribution\nAssistant-initiated.",
            "merged_at": "2026-08-19T04:00:00Z",
            "html_url": "https://example.test/82",
            "head": {"ref": "genesis/candidate-assisted"},
        },
        {
            "number": 70,
            "title": "Owner bootstrap",
            "body": "Owner-authorized bootstrap.",
            "merged_at": "2026-08-19T03:00:00Z",
            "html_url": "https://example.test/70",
            "head": {"ref": "owner/bootstrap"},
        },
    ]
    rows = attributed_development_prs(pulls)
    assert summarize(rows) == {"genesis_autonomous": 1, "assisted": 1, "owner": 1, "total": 3}
    assert {row["number"]: row["attribution"] for row in rows} == {
        90: "genesis_autonomous",
        82: "assisted",
        70: "owner",
    }
    assert len(merged_self_development_prs(pulls)) == 1


def test_manual_candidate_is_assisted_not_autonomous() -> None:
    pr = {
        "number": 81,
        "title": "Add safeguarded parallel autonomous development",
        "body": "## Goal\nAssistant-created improvement.",
        "merged_at": "2026-08-19T03:26:00Z",
        "head": {"ref": "genesis/privileged-candidate-parallel-development"},
    }
    assert classify_pr_attribution(pr) == "assisted"
    assert merged_self_development_prs([pr]) == []


def test_privileged_candidate_requires_explicit_autonomy_proof_marker() -> None:
    pr = {
        "number": 91,
        "title": "Privileged autonomous improvement",
        "body": f"{PROOF_MARKER}\n## Goal\nImprove guarded orchestration.",
        "merged_at": "2026-08-19T05:10:00Z",
        "head": {"ref": "genesis/privileged-candidate-guarded-orchestration"},
    }
    assert has_autonomous_provenance(pr) is True
    assert classify_pr_attribution(pr) == "genesis_autonomous"


def test_improvement_prefers_goal_section() -> None:
    pr = {"title": "Fallback title", "body": "## Goal\nMake failures less repetitive.\n\n## Changes\nAdd cooldown."}
    assert improvement_from_pr(pr) == "Make failures less repetitive."
