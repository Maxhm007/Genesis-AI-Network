from pathlib import Path

from genesis.autonomy_proof import AutonomyProofLedger
from genesis.modules.task_queue import PersistentTaskQueue
from genesis.self_evaluation import GenesisSelfEvaluation
from scripts.self_evaluation_dashboard import improvement_from_pr, merged_self_development_prs


def test_genesis_self_evaluation_counts_completed_development_task(tmp_path: Path) -> None:
    queue = PersistentTaskQueue(tmp_path / "runtime" / "genesis_tasks.sqlite3")
    task = queue.create("Improve autonomous task selection", module_id="genesis.coding", priority=80)
    queue.transition(task.task_id, "assigned")
    queue.transition(task.task_id, "running")
    queue.transition(task.task_id, "review")
    queue.transition(task.task_id, "complete")

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
    assert report["recent_completed_tasks"][0]["improved"] == "Improve autonomous task selection"
    assert report["recent_autonomous_improvements"][0]["improved"] == "Improve autonomous task selection"


def test_dashboard_history_counts_only_merged_genesis_candidates() -> None:
    pulls = [
        {
            "number": 81,
            "title": "Add safeguarded parallel autonomous development",
            "body": "## Goal\nIncrease Genesis development throughput safely.\n\n## Safety\nKeep serial promotion.",
            "merged_at": "2026-08-19T03:26:00Z",
            "html_url": "https://example.test/81",
            "head": {"ref": "genesis/privileged-candidate-parallel-development"},
        },
        {
            "number": 82,
            "title": "Unmerged candidate",
            "body": "## Goal\nNot done yet.",
            "merged_at": None,
            "head": {"ref": "genesis/candidate-unmerged"},
        },
        {
            "number": 83,
            "title": "Owner maintenance",
            "body": "## Goal\nExternal maintenance.",
            "merged_at": "2026-08-19T03:30:00Z",
            "head": {"ref": "owner/maintenance"},
        },
    ]
    history = merged_self_development_prs(pulls)
    assert len(history) == 1
    assert history[0]["number"] == 81
    assert history[0]["lane"] == "privileged"
    assert history[0]["improvement"] == "Increase Genesis development throughput safely."


def test_improvement_prefers_goal_section() -> None:
    pr = {"title": "Fallback title", "body": "## Goal\nMake failures less repetitive.\n\n## Changes\nAdd cooldown."}
    assert improvement_from_pr(pr) == "Make failures less repetitive."
