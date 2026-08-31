from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "genesis-oldest-issue-solver.yml"


def test_oldest_issue_solver_fetches_all_open_issue_pages():
    text = WORKFLOW.read_text(encoding="utf-8")

    assert "gh api --paginate" in text
    assert "--jq '.[]'" in text
    assert "| jq -s '.' > /tmp/genesis-open-issues.json" in text
    assert 'issues?state=open&sort=created&direction=asc&per_page=100' in text


def test_oldest_issue_solver_preserves_skip_boundaries():
    text = WORKFLOW.read_text(encoding="utf-8")

    assert "genesis-solver-exhausted" in text
    assert "Persistent communication/reporting channels are not work items." in text
    assert "protected_targets" in text
    assert "requires_measurement" in text
