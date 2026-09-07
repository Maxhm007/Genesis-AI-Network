from pathlib import Path

from scripts import dashboard_successor_identity as identity


def test_parent_issue_number_reads_repair_successor_marker():
    body = "<!-- genesis-unsolved-successor-of:733 -->\nrepair follow-up"
    assert identity.parent_issue_number(body) == 733
    assert identity.parent_issue_number("ordinary issue") is None


def test_inherit_dashboard_identity_copies_exact_marker_and_fingerprint():
    parent = """<!-- genesis-dashboard-review:625faf147b9889c6 -->
Genesis-Problem-Fingerprint: dashboard-review:625faf147b9889c6
"""
    successor = "<!-- genesis-unsolved-successor-of:733 -->\nrepair follow-up\n"

    updated = identity.inherit_dashboard_identity(successor, parent)

    assert "<!-- genesis-dashboard-review:625faf147b9889c6 -->" in updated
    assert "Genesis-Problem-Fingerprint: dashboard-review:625faf147b9889c6" in updated


def test_inherit_dashboard_identity_is_idempotent():
    parent = """<!-- genesis-dashboard-review:1988e5f502a4f940 -->
Genesis-Problem-Fingerprint: dashboard-review:1988e5f502a4f940
"""
    successor = """<!-- genesis-unsolved-successor-of:734 -->
<!-- genesis-dashboard-review:1988e5f502a4f940 -->
Genesis-Problem-Fingerprint: dashboard-review:1988e5f502a4f940
"""

    assert identity.inherit_dashboard_identity(successor, parent) == successor


def test_non_dashboard_parent_does_not_change_successor():
    successor = "<!-- genesis-unsolved-successor-of:500 -->\nrepair follow-up\n"
    assert identity.inherit_dashboard_identity(successor, "ordinary parent") == successor


def test_successor_identity_workflow_contract():
    workflow = Path(".github/workflows/genesis-dashboard-successor-identity.yml").read_text(
        encoding="utf-8"
    )
    assert "types: [opened]" in workflow
    assert "issues: write" in workflow
    assert "contents: read" in workflow
    assert "genesis-unsolved-successor-of:" in workflow
    assert "python scripts/dashboard_successor_identity.py" in workflow
