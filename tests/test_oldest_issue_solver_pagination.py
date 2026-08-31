from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONTROLLER = ROOT / ".github" / "workflows" / "genesis-sequential-issue-controller.yml"
OLDEST = ROOT / ".github" / "workflows" / "genesis-oldest-issue-solver.yml"
PRIORITY = ROOT / ".github" / "workflows" / "genesis-priority-issue-solver.yml"


def test_sequential_controller_fetches_all_open_issue_pages():
    text = CONTROLLER.read_text(encoding="utf-8")

    assert "gh api --paginate" in text
    assert "--jq '.[]'" in text
    assert "| jq -s '.' > /tmp/genesis-controller-open.json" in text


def test_sequential_controller_preserves_skip_boundaries():
    text = CONTROLLER.read_text(encoding="utf-8")

    assert "genesis-solver-exhausted" in text
    assert "lower_title.startswith(('genesis chat:', '[genesis hourly report]', '[genesis gene chat]'))" in text
    assert "'persistent github-native reporting channel' in lower_body" in text
    assert "protected_targets" in text
    assert "requires_measurement" in text
    assert "external-authority / independent-secret provisioning blocker" in text


def test_legacy_solver_entrypoints_do_not_scan_or_claim_the_queue():
    oldest = OLDEST.read_text(encoding="utf-8")
    priority = PRIORITY.read_text(encoding="utf-8")

    for text in (oldest, priority):
        assert "genesis-sequential-issue-controller.yml" in text
        assert "gh api --paginate" not in text
        assert "genesis-repair-in-progress" not in text
        assert "genesis-bounded-repair-worker.yml" not in text
