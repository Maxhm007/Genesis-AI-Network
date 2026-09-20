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


def test_sequential_controller_preserves_safety_boundaries_without_skipping_work_classes():
    workflow = CONTROLLER.read_text(encoding="utf-8")
    selector = (ROOT / "scripts" / "sequential_issue_selector.py").read_text(encoding="utf-8")

    assert "genesis-solver-exhausted" in selector
    assert "genesis-deferred" in workflow
    assert 'lower_title.startswith(("genesis chat:", "[genesis hourly report]", "[genesis gene chat]"))' in selector
    assert '"persistent github-native reporting channel" in lower_body' in selector
    assert "PROTECTED_TARGETS" in selector
    assert "python -m genesis.github_issue_cleanup" in workflow
    assert "requires_measurement" not in selector
    assert "external-authority / independent-secret provisioning blocker" not in selector


def test_sequential_controller_prioritizes_concrete_repairs_before_general_work():
    text = (ROOT / "scripts" / "sequential_issue_selector.py").read_text(encoding="utf-8")

    assert "issue_value_score" in text
    assert "lane_bonus" in text
    assert 'lower_title.startswith(("[genesis detected]", "[genesis repair]"))' in text
    assert '"genesis-repair"' in text
    assert '"task3-failed-autonomy"' in text
    assert "ranked.sort" in text
    assert '"selected": ranked[0] if ranked else None' in text


def test_legacy_solver_entrypoints_are_retired():
    assert not OLDEST.exists()
    assert not PRIORITY.exists()
