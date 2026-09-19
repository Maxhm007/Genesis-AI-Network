from genesis.issue_tag_manager import (
    canonicalize_issue_tags,
    is_genesis_owned,
    retired_genesis_labels,
)

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

def test_obsolete_alias_is_migrated_to_canonical_label():
    plan = canonicalize_issue_tags(issue("genesis-in-progress"))
    assert "genesis-in-progress" in plan.remove
    assert "genesis-working" in plan.add

def test_genesis_cannot_own_manual_protected_labels():
    assert is_genesis_owned("genesis-custom") is True
    assert is_genesis_owned("security") is False
    assert is_genesis_owned("owner-priority") is False

def test_only_unused_unknown_genesis_labels_are_retired():
    existing = {"genesis-autonomous", "genesis-old-unused", "genesis-old-used", "security", "bug"}
    used = {"genesis-old-used"}
    assert retired_genesis_labels(existing, used) == ("genesis-old-unused",)
