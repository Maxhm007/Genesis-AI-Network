from pathlib import Path


def test_exhausted_requeue_wakes_on_hard_repair_intelligence_change() -> None:
    root = Path(__file__).resolve().parents[1]
    workflow = (root / ".github/workflows/genesis-exhausted-issue-requeue.yml").read_text(encoding="utf-8")

    assert "- genesis/github_issue_capability_builder.py" in workflow
    assert "concurrency:\n  group: genesis-exhausted-issue-requeue\n  cancel-in-progress: false" in workflow
    assert "GENESIS_EXHAUSTED_REQUEUE_LIMIT: '5'" in workflow
    assert "gh workflow run genesis-sequential-issue-controller.yml" in workflow
