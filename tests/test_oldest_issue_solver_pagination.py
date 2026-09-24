from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OLDEST = ROOT / ".github/workflows/genesis-oldest-issue-solver.yml"
PRIORITY = ROOT / ".github/workflows/genesis-priority-issue-solver.yml"


def test_agentic_dispatch_fetches_all_issue_pages():
    source = (ROOT / "scripts/agentic_lab_recovery_dispatch.py").read_text(encoding="utf-8")
    assert "for page in range(1, 101)" in source
    assert "per_page=100&page={page}" in source


def test_agentic_dispatch_preserves_safety_boundaries():
    source = (ROOT / "scripts/agentic_lab_recovery_dispatch.py").read_text(encoding="utf-8")
    assert "PROTECTED_TARGETS" in source
    assert "genesis-waiting-capability" in source
    assert "genesis-needs-human" in source
    assert "local_claim_block_reason" in source


def test_legacy_solver_entrypoints_are_retired():
    assert not OLDEST.exists()
    assert not PRIORITY.exists()
