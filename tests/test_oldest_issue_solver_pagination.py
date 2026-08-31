from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OLDEST = ROOT / ".github" / "workflows" / "genesis-oldest-issue-solver.yml"
PRIORITY = ROOT / ".github" / "workflows" / "genesis-priority-issue-solver.yml"


def test_issue_solvers_fetch_all_open_issue_pages():
    oldest = OLDEST.read_text(encoding="utf-8")
    priority = PRIORITY.read_text(encoding="utf-8")

    assert "gh api --paginate" in oldest
    assert "--jq '.[]'" in oldest
    assert "| jq -s '.' > /tmp/genesis-open-issues.json" in oldest

    assert "gh api --paginate" in priority
    assert "--jq '.[]'" in priority
    assert "| jq -s '.' > /tmp/genesis-priority-open-issues.json" in priority


def test_oldest_issue_solver_preserves_skip_boundaries():
    text = OLDEST.read_text(encoding="utf-8")

    assert "genesis-solver-exhausted" in text
    assert "Persistent communication/reporting channels are not work items." in text
    assert "protected_targets" in text
    assert "requires_measurement" in text


def test_priority_issue_solver_preserves_skip_boundaries():
    text = PRIORITY.read_text(encoding="utf-8")

    assert "genesis-priority-exhausted" in text
    assert "protected_targets" in text
    assert "requires_measurement" in text
