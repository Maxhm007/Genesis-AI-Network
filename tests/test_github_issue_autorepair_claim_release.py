from pathlib import Path


AUTOREPAIR = Path(".github/workflows/github-issue-autorepair.yml")
HEARTBEAT = Path(".github/workflows/github-issue-autorepair-heartbeat.yml")


def test_no_candidate_claim_is_released_before_serialized_integration() -> None:
    text = AUTOREPAIR.read_text(encoding="utf-8")

    assert "release_unvalidated_claim:" in text
    assert "needs: [plan, solve_workers]" in text
    assert "Release reservation immediately when solve produced no validating candidate" in text
    assert 'index("genesis-validating")' in text
    assert "integration retains the reservation" in text
    assert "--remove-label genesis-repair-in-progress" in text

    release_at = text.index("release_unvalidated_claim:")
    integrate_at = text.index("integrate_workers:")
    assert release_at < integrate_at


def test_refill_waits_for_claim_cleanup_and_integration() -> None:
    text = AUTOREPAIR.read_text(encoding="utf-8")

    assert "needs: [plan, solve_workers, release_unvalidated_claim, integrate_workers]" in text
    assert "Immediately wake read-only heartbeat to refill repair capacity" in text


def test_heartbeat_reclaims_only_old_unvalidated_claims() -> None:
    text = HEARTBEAT.read_text(encoding="utf-8")

    assert "GENESIS_ISSUE_REPAIR_STALE_MINUTES: '60'" in text
    assert "issues: write" in text
    assert "Reclaim stale unvalidated reservations and wake available lanes" in text
    assert 'index("genesis-repair-in-progress")' in text
    assert 'index("genesis-validating")) == null' in text
    assert '(.updatedAt // "") < $cutoff' in text
    assert "Re-read immediately before mutation" in text
    assert "--remove-label genesis-repair-in-progress" in text


def test_heartbeat_reloads_issue_snapshot_after_reclamation() -> None:
    text = HEARTBEAT.read_text(encoding="utf-8")

    assert "snapshot_issues()" in text
    assert text.count("snapshot_issues") >= 3  # declaration + before + after reclamation
    assert "Capacity must be computed from a fresh snapshot after reclamation." in text
    fresh_snapshot = text.index("# Capacity must be computed from a fresh snapshot after reclamation.")
    active_count = text.index("active=$(jq")
    assert fresh_snapshot < active_count
