"""Safety regression for the bounded repair workflow activation."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/genesis-bounded-repair-worker.yml"


def test_repair_job_is_enabled_only_after_test_first_gate():
    workflow = WORKFLOW.read_text(encoding="utf-8")
    gate = workflow.index("  test-first-gate:")
    worker = workflow.index("  repair-and-promote:")
    assert gate < worker
    section = workflow[worker:]
    assert "needs: test-first-gate" in section
    assert "needs.test-first-gate.outputs.eligible == 'true'" in section
    assert "if: false" not in section


def test_gate_checks_issue_reservation_before_expensive_model():
    workflow = WORKFLOW.read_text(encoding="utf-8")
    gate = workflow.split("  repair-and-promote:")[0]
    assert "genesis-repair-in-progress" in gate
    assert "gh issue view" in gate
    assert "genesis.issue_target" in gate
    assert "Test repair control plane before any model starts" in gate
    assert "tests/test_issue_solver.py" in gate
    assert "tests/test_repair_checkpoints.py" in gate


def test_existing_full_validation_and_verification_remain():
    worker = WORKFLOW.read_text(encoding="utf-8").split("  repair-and-promote:")[1]
    assert "Verify clean repository baseline" in worker
    assert "python -m pytest -q" in worker
    assert "Independently validate and promote exact candidate" in worker
    assert "genesis.learned_capability_acceptance" in worker
    assert "genesis-issue-closure-manager.yml" in worker
