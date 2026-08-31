from pathlib import Path


SOLVER = Path(".github/workflows/genesis-oldest-issue-solver.yml")
WORKER = Path(".github/workflows/genesis-bounded-repair-worker.yml")


def test_solver_reserves_issue_before_dispatching_repair_worker() -> None:
    text = SOLVER.read_text(encoding="utf-8")

    assert "genesis-repair-in-progress" in text
    assert "genesis-bounded-repair-worker.yml" in text
    assert "gh workflow run" in text
    assert '-f issue_number="$issue_number"' in text


def test_solver_does_not_reclaim_active_repair_reservation() -> None:
    text = SOLVER.read_text(encoding="utf-8")

    assert "genesis-repair-in-progress" in text
    assert "if labels & {'genesis-claimed', 'genesis-working', 'genesis-verifying', 'genesis-repair-in-progress', 'genesis-validating', 'genesis-priority-claim'}:" in text


def test_worker_requires_exact_reservation_before_code_work() -> None:
    text = WORKER.read_text(encoding="utf-8")

    assert 'index("genesis-repair-in-progress")' in text
    assert 'state=$(jq -r' in text
    assert 'safe=false' in text
    assert "No code was changed" in text


def test_unsuccessful_worker_always_releases_reservation() -> None:
    text = WORKER.read_text(encoding="utf-8")

    release_at = text.index("Release unsuccessful reservation safely")
    release = text[release_at:]
    assert "if: always()" in release
    assert "--remove-label genesis-repair-in-progress" in release
    assert "issue remains open for the bounded retry policy" in release


def test_worker_marks_exhausted_attempt_and_allows_queue_to_move() -> None:
    text = WORKER.read_text(encoding="utf-8")

    release_at = text.index("Release unsuccessful reservation safely")
    release = text[release_at:]
    assert 'solver_attempt=$(gh api' in release
    assert '"$solver_attempt" -ge 3' in release
    assert "--add-label genesis-solver-exhausted" in release
    assert "bounded attempts exhausted; queue will move on" in release


def test_successful_promotion_releases_active_labels_only_after_verification() -> None:
    text = WORKER.read_text(encoding="utf-8")

    verify_at = text.index("python -m pytest -q", text.index("git reset --hard origin/main"))
    label_at = text.index("genesis-verified", verify_at)
    release_at = text.index("genesis-repair-in-progress", label_at)
    close_at = text.index("state=closed", release_at)
    assert verify_at < label_at < release_at < close_at
