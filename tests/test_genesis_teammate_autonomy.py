from scripts.genesis_teammate import classify


def test_autonomous_issue_objective_routes_to_recovery_for_stuck_work():
    assert classify("Autonomous Genesis development task: workflow is stuck and retry failed") == "recovery"


def test_autonomous_issue_objective_routes_to_sentinel_for_validation():
    assert classify("Autonomous Genesis development task: validate test regression") == "sentinel"


def test_autonomous_issue_objective_routes_to_atlas_for_architecture():
    assert classify("Autonomous Genesis development task: redesign architecture") == "atlas"


def test_autonomous_issue_objective_defaults_to_forge():
    assert classify("Autonomous Genesis development task: implement bounded fix") == "forge"
