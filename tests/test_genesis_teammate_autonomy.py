from scripts.genesis_teammate import classify


def test_autonomous_issue_objective_routes_to_recovery_for_stuck_work():
    assert classify("Autonomous Genesis development task: workflow is stuck and retry failed") == "recovery"


def test_autonomous_issue_objective_routes_to_sentinel_for_validation():
    assert classify("Autonomous Genesis development task: validate test regression") == "sentinel"


def test_autonomous_issue_objective_routes_to_atlas_for_architecture():
    assert classify("Autonomous Genesis development task: redesign architecture") == "atlas"


def test_autonomous_issue_objective_defaults_to_forge():
    assert classify("Autonomous Genesis development task: implement bounded fix") == "forge"


def test_teammate_skips_owner_paused_issue(monkeypatch):
    import scripts.genesis_teammate as module
    paused = {'number': 867, 'title': 'Health controller', 'body': 'Fix health', 'labels': [{'name': 'genesis-owner-paused'}]}
    monkeypatch.setattr(module, 'open_development_issues', lambda: [paused])
    monkeypatch.setattr(module, 'autonomous_claim_exists', lambda number: False)
    assert module.select_autonomous_issue() is None
