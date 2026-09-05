from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_bounded_worker_terminally_defers_exhausted_issue() -> None:
    text = (ROOT / ".github/workflows/genesis-bounded-repair-worker.yml").read_text(encoding="utf-8")

    assert "--add-label genesis-deferred" in text
    assert "-f state=closed -f state_reason=not_planned" in text
    assert "changed repair engine may reopen it automatically" in text


def test_requeue_wakes_authoritative_sequential_controller() -> None:
    text = (ROOT / ".github/workflows/genesis-exhausted-issue-requeue.yml").read_text(encoding="utf-8")

    assert "--workflow genesis-sequential-issue-controller.yml" in text
    assert "gh workflow run genesis-sequential-issue-controller.yml" in text
    assert "genesis-oldest-issue-solver.yml" not in text
