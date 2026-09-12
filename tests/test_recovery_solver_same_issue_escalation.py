from pathlib import Path


def test_recovery_solver_never_creates_repair_successor():
    source = Path("scripts/recovery_solver_dispatch.py").read_text(encoding="utf-8")
    assert "create_successor_handoff" not in source
    assert "successor_created_and_parent_closed" not in source
    assert "same_issue_agentic_lab_escalation" in source
    assert 'RECOVERY_ESCALATED_LABEL = "genesis-agentic-escalated"' in source
    assert "No repair follow-up/successor Issue is created." in source


def test_recovery_solver_stops_reclaiming_escalated_issue():
    source = Path("scripts/recovery_solver_dispatch.py").read_text(encoding="utf-8")
    assert "if RECOVERY_ESCALATED_LABEL in issue_labels:" in source
    assert "continue" in source
