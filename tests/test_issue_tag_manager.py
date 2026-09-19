from genesis.issue_tag_manager import canonicalize_issue_tags

def issue(*labels):
    return {"labels": [{"name": label} for label in labels]}

def test_terminal_state_clears_active_execution_tags():
    plan = canonicalize_issue_tags(issue("genesis-verified", "genesis-working", "genesis-repair-in-progress", "genesis-autonomous"))
    assert "genesis-working" in plan.remove
    assert "genesis-repair-in-progress" in plan.remove
    assert "genesis-autonomous" in plan.remove

def test_only_most_advanced_lifecycle_state_survives():
    plan = canonicalize_issue_tags(issue("genesis-claimed", "genesis-working", "genesis-validating"))
    assert set(plan.remove) == {"genesis-claimed", "genesis-working"}

def test_exhausted_issue_gets_agentic_owner():
    plan = canonicalize_issue_tags(issue("genesis-solver-exhausted"))
    assert plan.add == ("agentic-lab",)

def test_repair_reservation_requires_autonomous_authority():
    plan = canonicalize_issue_tags(issue("genesis-repair-in-progress"))
    assert plan.add == ("genesis-autonomous",)
