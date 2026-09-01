from pathlib import Path


CONTROLLER = Path(".github/workflows/genesis-sequential-issue-controller.yml")
WORKER = Path(".github/workflows/genesis-bounded-repair-worker.yml")
REPAIR_ENGINE = Path("scripts/github_issue_autorepair.py")


def test_controller_keeps_issue_selection_single_lane() -> None:
    text = CONTROLLER.read_text(encoding="utf-8")

    assert "group: genesis-sequential-issue-controller" in text
    assert "cancel-in-progress: false" in text
    assert "max_attempts=3" in text
    assert "cron: '*/10 * * * *'" in text
    assert "Claiming exactly one issue" in text


def test_worker_is_per_issue_serialized_and_bounded() -> None:
    text = WORKER.read_text(encoding="utf-8")

    assert "group: genesis-bounded-repair-${{ inputs.issue_number }}" in text
    assert "cancel-in-progress: false" in text
    assert "timeout-minutes: 90" in text
    assert "issue_number:" in text


def test_worker_uses_existing_guarded_repair_engine() -> None:
    worker = WORKER.read_text(encoding="utf-8")
    engine = REPAIR_ENGINE.read_text(encoding="utf-8")

    assert "python scripts/github_issue_autorepair.py" in worker
    assert "SelfDevelopmentExecutor" in engine
    assert "allowed_issue_repair_paths" in engine
    assert "restricted_issue_targets" in engine
    assert "MAX_VALIDATION_ATTEMPTS = 3" in engine


def test_worker_uses_free_replaceable_bounded_coder() -> None:
    text = WORKER.read_text(encoding="utf-8")

    assert "Qwen/Qwen2.5-Coder-0.5B-Instruct" in text
    assert "Qwen/Qwen2.5-Coder-1.5B-Instruct" in text
    assert "GENESIS_PROVIDER_MAX_NEW_TOKENS: '512'" in text
    assert "GENESIS_REPAIR_ESCALATION_MAX_NEW_TOKENS: '512'" in text
    assert "GENESIS_PROVIDER_TIMEOUT_SECONDS: '300'" in text
    assert "scripts/pulse_coding_provider.py" in text


def test_worker_blocks_control_plane_targets() -> None:
    text = WORKER.read_text(encoding="utf-8")

    assert '"$target" != genesis/*.py' in text
    assert "genesis/security.py" in text
    assert "genesis/selfdev.py" in text
    assert "genesis/issue_solver.py" in text
    assert "genesis/autonomy_guard.py" in text
    assert "No code was changed" in text


def test_candidate_scope_is_exact_target_plus_matching_test() -> None:
    text = WORKER.read_text(encoding="utf-8")

    assert 'target_test="tests/test_$(basename "$TARGET" .py).py"' in text
    assert 'if [[ "$path" != "$TARGET" && "$path" != "$target_test" ]]' in text
    assert "Rejected out-of-scope candidate path" in text


def test_promotion_requires_fresh_full_validation_and_exact_main_push() -> None:
    text = WORKER.read_text(encoding="utf-8")

    assert "python -m py_compile \"$TARGET\"" in text
    assert 'python -m pytest -q "$target_test"' in text
    assert text.count("python -m pytest -q") >= 3
    assert "for integration_attempt in 1 2 3" in text
    assert 'git cherry-pick "$CANDIDATE_SHA"' in text
    assert 'latest_main=$(git rev-parse origin/main)' in text
    assert 'git push origin HEAD:main' in text


def test_issue_closes_only_after_post_promotion_verification() -> None:
    text = WORKER.read_text(encoding="utf-8")

    reset_at = text.index("git reset --hard origin/main")
    final_tests_at = text.index("python -m pytest -q", reset_at)
    verified_at = text.index("--add-label genesis-verified", final_tests_at)
    close_at = text.index("state=closed", verified_at)

    assert reset_at < final_tests_at < verified_at < close_at
