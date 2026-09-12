from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_bounded_worker_escalates_exhausted_issue_without_closing() -> None:
    text = (ROOT / ".github/workflows/genesis-bounded-repair-worker.yml").read_text(encoding="utf-8")

    release_at = text.index("Release unsuccessful reservation safely")
    release = text[release_at:]
    assert "--add-label genesis-solver-exhausted" in release
    assert "--add-label agentic-lab" in release
    assert "same authoritative Issue remains OPEN under Agentic Lab" in release
    assert "-f state=closed -f state_reason=not_planned" not in release


def test_requeue_wakes_authoritative_sequential_controller() -> None:
    text = (ROOT / ".github/workflows/genesis-exhausted-issue-requeue.yml").read_text(encoding="utf-8")

    assert "--workflow genesis-sequential-issue-controller.yml" in text
    assert "gh workflow run genesis-sequential-issue-controller.yml" in text
    assert "genesis-oldest-issue-solver.yml" not in text
