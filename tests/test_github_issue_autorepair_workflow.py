from pathlib import Path


DISPATCHER = Path(".github/workflows/github-issue-autorepair.yml")
SOLVER = Path(".github/workflows/github-issue-autorepair-worker.yml")
INTEGRATION = Path(".github/workflows/github-issue-autorepair-integration.yml")


def test_dispatcher_admits_three_parallel_solvers_but_one_integration_pipeline() -> None:
    text = DISPATCHER.read_text(encoding="utf-8")

    assert "GENESIS_ISSUE_REPAIR_MAX_PARALLEL: '3'" in text
    assert "group: genesis-github-issue-autorepair-admission" in text
    assert "solve_workers:" in text
    assert "max-parallel: 3" in text
    assert "github-issue-autorepair-worker.yml" in text
    assert "integrate_workers:" in text
    assert "max-parallel: 1" in text
    assert "github-issue-autorepair-integration.yml" in text


def test_dispatcher_refill_is_bounded_and_has_five_minute_fallback() -> None:
    text = DISPATCHER.read_text(encoding="utf-8")

    assert "cron: '*/5 * * * *'" in text
    assert "refill_round" in text
    assert "needs.plan.outputs.refill_round == '0'" in text
    assert "-f refill_round=1" in text
    assert "actions: write" in text
    assert "active < GENESIS_ISSUE_REPAIR_MAX_PARALLEL" in text
    assert 'index("genesis-repair-in-progress")' in text
    assert 'index("genesis-validating")' in text


def test_dispatcher_rolls_back_partial_claims() -> None:
    text = DISPATCHER.read_text(encoding="utf-8")

    assert "rollback_uncommitted_claims" in text
    assert "trap rollback_uncommitted_claims EXIT" in text
    assert "claims_committed='true'" in text
    assert "--add-label genesis-repair-in-progress" in text


def test_solver_keeps_reservation_until_serialized_integration() -> None:
    text = SOLVER.read_text(encoding="utf-8")

    assert "group: genesis-github-issue-autorepair-issue-${{ inputs.issue_number }}" in text
    assert 'index("genesis-repair-in-progress")' in text
    assert "--issue-number '${{ inputs.issue_number }}'" in text
    assert "--remove-label genesis-repair-in-progress" not in text
    assert "intentionally not released here" in text


def test_integration_rebases_onto_latest_main_before_all_validation() -> None:
    text = INTEGRATION.read_text(encoding="utf-8")

    rebase_at = text.index("git rebase origin/main")
    validator_a_at = text.index("validator_a:")
    validator_b_at = text.index("validator_b:")
    secret_guard_at = text.index("secret_guard:")

    assert rebase_at < validator_a_at
    assert rebase_at < validator_b_at
    assert rebase_at < secret_guard_at
    assert '--force-with-lease="refs/heads/$branch:$old_sha"' in text
    assert "All independent validation is being repeated on this exact SHA" in text


def test_integration_preserves_independent_validation_security_and_exact_sha_promotion() -> None:
    text = INTEGRATION.read_text(encoding="utf-8")

    assert "Independent full test suite A" in text
    assert "Independent full test suite B" in text
    assert "Security review A" in text
    assert "Security review B" in text
    assert "Scan candidate and reachable history for secrets" in text
    assert "Verify independent signed quorum" in text
    assert "group: genesis-github-issue-autorepair-promotion" in text
    assert 'git merge-base --is-ancestor "$main_sha" "$CANDIDATE_SHA"' in text
    assert 'git push origin "$CANDIDATE_SHA:refs/heads/main"' in text


def test_claim_is_released_only_after_integration_pipeline_finishes() -> None:
    text = INTEGRATION.read_text(encoding="utf-8")

    assert "release_claim:" in text
    assert "if: always()" in text
    assert "Release this issue reservation only after its integration pipeline ends" in text
    assert "--remove-label genesis-repair-in-progress" in text


def test_parallel_artifacts_are_issue_scoped() -> None:
    solver = SOLVER.read_text(encoding="utf-8")
    integration = INTEGRATION.read_text(encoding="utf-8")

    assert "genesis-github-issue-autorepair-${{ inputs.issue_number }}-${{ github.run_id }}" in solver
    assert "github-issue-validator-a-${{ inputs.issue_number }}-${{ github.run_id }}" in integration
    assert "github-issue-validator-b-${{ inputs.issue_number }}-${{ github.run_id }}" in integration
