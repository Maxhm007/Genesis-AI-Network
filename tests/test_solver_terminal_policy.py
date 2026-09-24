from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_bounded_worker_escalates_without_false_closure() -> None:
    text = (ROOT / ".github/workflows/genesis-bounded-repair-worker.yml").read_text(encoding="utf-8")
    release = text[text.index("Release unsuccessful reservation safely"):]
    assert "--add-label genesis-solver-exhausted" in release
    assert "--add-label agentic-lab" in release
    assert "same authoritative Issue remains OPEN under Agentic Lab" in release
    assert "-f state=closed -f state_reason=not_planned" not in release


def test_exhausted_requeue_wakes_agentic_lab_only() -> None:
    text = (ROOT / ".github/workflows/genesis-exhausted-issue-requeue.yml").read_text(encoding="utf-8")
    assert "gh workflow run genesis-agentic-lab-recovery.yml" in text
    assert "genesis-sequential-issue-controller.yml" not in text
