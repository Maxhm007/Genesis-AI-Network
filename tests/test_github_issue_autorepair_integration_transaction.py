from pathlib import Path


WORKER = Path(".github/workflows/genesis-bounded-repair-worker.yml")


def test_integration_transaction_is_serialized_per_issue() -> None:
    text = WORKER.read_text(encoding="utf-8")

    transaction_lock = "group: genesis-bounded-repair-${{ inputs.issue_number }}"
    assert transaction_lock in text
    assert text.index(transaction_lock) < text.index("jobs:")
    assert "cancel-in-progress: false" in text


def test_integration_rebuilds_candidate_on_latest_main() -> None:
    text = WORKER.read_text(encoding="utf-8")

    assert "for integration_attempt in 1 2 3" in text
    assert "git fetch origin main" in text
    assert 'git checkout -B "genesis/integration-${ISSUE_NUMBER}-${GITHUB_RUN_ID}" origin/main' in text
    assert 'git cherry-pick "$CANDIDATE_SHA"' in text
    assert 'integrated_base=$(git rev-parse HEAD^)' in text
    assert 'latest_main=$(git rev-parse origin/main)' in text
    assert "main moved during validation; rebuilding on latest main" in text


def test_integration_requires_exact_scope_and_full_regression_evidence() -> None:
    text = WORKER.read_text(encoding="utf-8")

    assert "Rejected out-of-scope candidate path" in text
    assert "python -m py_compile \"$TARGET\"" in text
    assert 'python -m pytest -q "$target_test"' in text
    assert text.count("python -m pytest -q") >= 3


def test_exact_candidate_is_promoted_only_after_validation() -> None:
    text = WORKER.read_text(encoding="utf-8")

    candidate_at = text.index('git cat-file -e "${CANDIDATE_SHA}^{commit}"')
    tests_at = text.index("python -m pytest -q", candidate_at)
    push_at = text.index("git push origin HEAD:main", tests_at)
    post_reset_at = text.index("git reset --hard origin/main", push_at)
    close_at = text.index("state=closed", post_reset_at)

    assert candidate_at < tests_at < push_at < post_reset_at < close_at
