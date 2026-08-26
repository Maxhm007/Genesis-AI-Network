from pathlib import Path


DISPATCHER = Path(".github/workflows/github-issue-autorepair.yml")
WORKER = Path(".github/workflows/github-issue-autorepair-worker.yml")


def test_dispatcher_uses_bounded_three_worker_admission() -> None:
    text = DISPATCHER.read_text(encoding="utf-8")

    assert "GENESIS_ISSUE_REPAIR_MAX_PARALLEL: '3'" in text
    assert "group: genesis-github-issue-autorepair-admission" in text
    assert "max-parallel: 3" in text
    assert "scripts/select_issue_repair_batch.py" in text
    assert "--add-label genesis-repair-in-progress" in text
    assert "github-issue-autorepair-worker.yml" in text


def test_dispatcher_refill_is_bounded_and_has_five_minute_fallback() -> None:
    text = DISPATCHER.read_text(encoding="utf-8")

    assert "cron: '*/5 * * * *'" in text
    assert "refill_round" in text
    assert "needs.plan.outputs.refill_round == '0'" in text
    assert "-f refill_round=1" in text
    assert "actions: write" in text
    assert "active < GENESIS_ISSUE_REPAIR_MAX_PARALLEL" in text


def test_dispatcher_rolls_back_partial_claims_and_cleans_failed_workers() -> None:
    text = DISPATCHER.read_text(encoding="utf-8")

    assert "rollback_uncommitted_claims" in text
    assert "trap rollback_uncommitted_claims EXIT" in text
    assert "claims_committed='true'" in text
    assert "cleanup_claims:" in text
    assert "if: always() && needs.plan.outputs.has_work == 'true'" in text
    assert "Release any batch claims left behind by failed workers" in text
    assert "--remove-label genesis-repair-in-progress" in text


def test_worker_preserves_claim_release_and_exact_issue_isolation() -> None:
    text = WORKER.read_text(encoding="utf-8")

    assert "group: genesis-github-issue-autorepair-issue-${{ inputs.issue_number }}" in text
    assert 'index("genesis-repair-in-progress")' in text
    assert "if: always()" in text
    assert "--remove-label genesis-repair-in-progress" in text
    assert "--issue-number '${{ inputs.issue_number }}'" in text


def test_worker_preserves_independent_validation_security_and_exact_sha_promotion() -> None:
    text = WORKER.read_text(encoding="utf-8")

    assert "Independent full test suite A" in text
    assert "Independent full test suite B" in text
    assert "Security review A" in text
    assert "Security review B" in text
    assert "Scan candidate and reachable history for secrets" in text
    assert "Verify independent signed quorum" in text
    assert "group: genesis-github-issue-autorepair-promotion" in text
    assert 'git merge-base --is-ancestor "$main_sha" "$CANDIDATE_SHA"' in text
    assert 'git push origin "$CANDIDATE_SHA:refs/heads/main"' in text


def test_parallel_workers_use_issue_scoped_artifact_names() -> None:
    text = WORKER.read_text(encoding="utf-8")

    assert "genesis-github-issue-autorepair-${{ inputs.issue_number }}-${{ github.run_id }}" in text
    assert "github-issue-validator-a-${{ inputs.issue_number }}-${{ github.run_id }}" in text
    assert "github-issue-validator-b-${{ inputs.issue_number }}-${{ github.run_id }}" in text
