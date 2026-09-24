from pathlib import Path


def test_exhausted_requeue_is_agentic_lab_feeder_only() -> None:
    root = Path(__file__).resolve().parents[1]
    workflow = (root / ".github/workflows/genesis-exhausted-issue-requeue.yml").read_text(encoding="utf-8")
    assert "Agentic Lab owns exhausted-issue re-arm and recovery state" in workflow
    assert "gh workflow run genesis-agentic-lab-recovery.yml" in workflow
    assert "issues: write" not in workflow
    assert "python scripts/requeue_exhausted_issues.py" not in workflow
