from pathlib import Path


DISPATCHER = Path(".github/workflows/github-issue-autorepair.yml")
SOLVER = Path(".github/workflows/github-issue-autorepair-worker.yml")
INTEGRATION = Path(".github/workflows/github-issue-autorepair-integration.yml")


def test_dispatcher_serializes_one_global_repair_lane() -> None:
    text = DISPATCHER.read_text(encoding="utf-8")

    assert "GENESIS_ISSUE_REPAIR_MAX_PARALLEL: '1'" in text
    assert "issue_number:" in text
    assert "group: genesis-autonomous-single-lane" in text
    assert "group: genesis-github-issue-autorepair-admission" in text
    assert "solve_workers:" in text
    assert text.count("max-parallel: 1") >= 3
    assert "github-issue-autorepair-worker.yml" in text
    assert "integrate_workers:" in text
    assert "github-issue-autorepair-integration.yml" in text


def test_dispatcher_refill_wakes_read_only_heartbeat() -> None:
    text = DISPATCHER.read_text(encoding="utf-8")

    assert "refill:" in text
    assert "actions: write" in text
    assert "gh workflow run github-issue-autorepair-heartbeat.yml" in text
    assert "--ref main" in text


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


def test_solver_uses_bounded_qwen_coder_retry_escalation() -> None:
    text = SOLVER.read_text(encoding="utf-8")

    assert "GENESIS_PROVIDER_NAME: genesis-adaptive-github-issue-autorepair" in text
    assert "GENESIS_REPAIR_FALLBACK_MODEL:" in text
    assert "Qwen/Qwen2.5-Coder-0.5B-Instruct" in text
    assert "GENESIS_REPAIR_ESCALATION_MODEL:" in text
    assert "Qwen/Qwen2.5-Coder-1.5B-Instruct" in text
    assert "GENESIS_PROVIDER_MAX_NEW_TOKENS: '512'" in text
    assert "GENESIS_REPAIR_ESCALATION_MAX_NEW_TOKENS: '512'" in text
    assert "GENESIS_PROVIDER_TIMEOUT_SECONDS: '300'" in text
    assert "scripts/pulse_coding_provider.py" in text
    assert '--model "$GENESIS_REPAIR_FALLBACK_MODEL"' in text
    assert '--escalation-model "$GENESIS_REPAIR_ESCALATION_MODEL"' in text
    assert '--escalation-max-new-tokens "$GENESIS_REPAIR_ESCALATION_MAX_NEW_TOKENS"' in text
    assert "snapshot_download(model_id)" in text
    assert "genesis-github-issue-autorepair-${{ runner.os }}-${{ steps.model_cache_key.outputs.model_key }}-v1" in text
    assert "scripts/local_reasoning_provider.py --model" not in text
    assert "deepseek-ai/DeepSeek-R1-Distill-Qwen-1.5B" not in text


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


def test_integration_tolerates_only_repository_policy_pr_creation_denial() -> None:
    text = INTEGRATION.read_text(encoding="utf-8")

    assert "Open or update exact candidate PR when repository policy permits" in text
    assert "GitHub Actions is not permitted to create or approve pull requests" in text
    assert "continuing with the same independently validated exact-SHA promotion path" in text
    assert 'cat "$RUNNER_TEMP/pr-create.err" >&2' in text
    assert "exit 1" in text
    assert "needs: [prepare, open_pr, validator_a, validator_b, secret_guard]" in text
    assert "PR_NUMBER: ${{ needs.open_pr.outputs.pr_number }}" in text


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
