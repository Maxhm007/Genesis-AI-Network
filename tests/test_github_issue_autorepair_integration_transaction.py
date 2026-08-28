from pathlib import Path


INTEGRATION = Path(".github/workflows/github-issue-autorepair-integration.yml")
DISPATCHER = Path(".github/workflows/github-issue-autorepair.yml")


def test_integration_transaction_is_serialized_from_rebase_through_promotion() -> None:
    text = INTEGRATION.read_text(encoding="utf-8")

    transaction_lock = "group: genesis-github-issue-autorepair-integration-transaction"
    assert transaction_lock in text
    assert text.index(transaction_lock) < text.index("jobs:")
    assert "cancel-in-progress: false" in text

    prepare_at = text.index("prepare:")
    rebase_at = text.index("git rebase origin/main")
    validator_a_at = text.index("validator_a:")
    validator_b_at = text.index("validator_b:")
    secret_guard_at = text.index("secret_guard:")
    promote_at = text.index("promote:")

    assert prepare_at < rebase_at < validator_a_at < promote_at
    assert rebase_at < validator_b_at < promote_at
    assert rebase_at < secret_guard_at < promote_at


def test_single_solver_lane_is_preserved() -> None:
    text = DISPATCHER.read_text(encoding="utf-8")

    assert "GENESIS_ISSUE_REPAIR_MAX_PARALLEL: '1'" in text
    assert "solve_workers:" in text
    assert "integrate_workers:" in text
