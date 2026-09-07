from pathlib import Path


def test_documented_agentic_recovery_invariant() -> None:
    text = Path("docs/agentic-recovery-lifecycle.md").read_text(encoding="utf-8")
    assert "failed repair method" in text
    assert "Issue open" in text
    assert "genesis-waiting-capability" in text
    assert "Only a verified and promoted target repair closes" in text
