from pathlib import Path


CONTROLLER = Path("scripts/agentic_lab_recovery_dispatch.py")
WORKER = Path(".github/workflows/genesis-bounded-repair-worker.yml")


def test_agentic_lab_reserves_issue_before_dispatching_worker() -> None:
    text = CONTROLLER.read_text(encoding="utf-8")
    reserve_at = text.index('claim_labels = ["genesis-autonomous", AGENTIC_LABEL]')
    dispatch_at = text.index('"/actions/workflows/genesis-agentic-strategy-worker.yml/dispatches"')
    assert reserve_at < dispatch_at
    assert 'claim_labels.insert(0, "genesis-repair-in-progress")' in text


def test_agentic_lab_respects_active_reservations() -> None:
    text = CONTROLLER.read_text(encoding="utf-8")
    assert "if issue_labels & ACTIVE_LABELS:" in text


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


def test_worker_escalates_exhausted_attempt_without_false_closure() -> None:
    text = WORKER.read_text(encoding="utf-8")

    release_at = text.index("Release unsuccessful reservation safely")
    release = text[release_at:]
    assert 'solver_attempt=$(gh api' in release
    assert '"$solver_attempt" -ge 3' in release
    assert "--add-label genesis-solver-exhausted" in release
    assert "--add-label agentic-lab" in release
    assert "--add-label genesis-agentic-escalated" in release
    assert "same authoritative Issue remains OPEN under Agentic Lab" in release
    assert "-f state=closed -f state_reason=not_planned" not in release


def test_successful_promotion_releases_active_labels_only_after_verification() -> None:
    text = WORKER.read_text(encoding="utf-8")

    verify_at = text.index("python -m pytest -q", text.index("git reset --hard origin/main"))
    label_at = text.index("genesis-verified", verify_at)
    release_at = text.index("genesis-repair-in-progress", label_at)
    close_at = text.index("genesis-issue-closure-manager.yml", release_at)
    assert verify_at < label_at < release_at < close_at
