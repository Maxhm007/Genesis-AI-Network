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


def test_dispatcher_reclaims_only_old_unvalidated_claims() -> None:
    text = AUTOREPAIR.read_text(encoding="utf-8")

    assert "GENESIS_ISSUE_REPAIR_STALE_MINUTES: '60'" in text
    assert "issues: write" in text
    assert "Reconcile stale claims, then build and claim one repair lane" in text
    assert 'index("genesis-repair-in-progress")' in text
    assert 'index("genesis-validating")) == null' in text
    assert '(.updatedAt // "") < $cutoff' in text
    assert 'stale_json=$(gh issue view "$stale_issue"' in text
    assert 'if [[ "$stale_now" == '\''true'\'' ]]; then' in text
    assert "--remove-label genesis-repair-in-progress" in text
    assert "snapshot_issues\n\n          selector=(python scripts/select_issue_repair_batch.py" in text
    assert text.count("snapshot_issues") >= 3


def test_heartbeat_detects_stale_claims_without_mutating_issues() -> None:
    text = HEARTBEAT.read_text(encoding="utf-8")

    assert "GENESIS_ISSUE_REPAIR_STALE_MINUTES: '60'" in text
    assert "issues: read" in text
    assert "issues: write" not in text
    assert "stale_count=$(jq" in text
    assert 'index("genesis-validating")) == null' in text
    assert '(.updatedAt // "") < $cutoff' in text
    assert "--remove-label genesis-repair-in-progress" not in text
    assert "gh issue edit" not in text


def test_saturated_stale_queue_wakes_authoritative_dispatcher_for_reconciliation() -> None:
    text = HEARTBEAT.read_text(encoding="utf-8")

    assert "elif (( stale_count > 0 )); then" in text
    assert "waking authoritative dispatcher for reconciliation" in text
    recovery_at = text.index("elif (( stale_count > 0 )); then")
    recovery_block = text[recovery_at:]
    assert "gh workflow run github-issue-autorepair.yml" in recovery_block
    assert "--ref main" in recovery_block
    assert '-f issue_number="$issue_number"' not in recovery_block
