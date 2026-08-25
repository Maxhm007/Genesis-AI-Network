from scripts.action_failure_watchdog import (
    actionable_run,
    decode_metadata,
    encode_metadata,
    failure_fingerprint,
    replace_metadata,
    sanitize_log_excerpt,
    select_actionable_run,
)


def _run(**overrides):
    base = {
        "id": 10,
        "status": "completed",
        "conclusion": "failure",
        "event": "schedule",
        "head_branch": "main",
        "updated_at": "2026-08-25T10:00:00Z",
    }
    base.update(overrides)
    return base


def test_action_failure_metadata_round_trip_and_replace():
    metadata = {"workflow_id": 9, "run_id": 11, "failed_job": "test", "failed_step": "pytest", "repair_cycles": 0}
    marker = encode_metadata(metadata)
    assert decode_metadata(marker)["run_id"] == 11
    updated = replace_metadata("body\n\n" + marker, {**metadata, "run_id": 12})
    assert decode_metadata(updated)["run_id"] == 12
    assert updated.count("genesis-action-failure") == 1


def test_actionable_run_ignores_pr_candidate_failures_and_current_watchdog():
    assert actionable_run(_run())
    assert not actionable_run(_run(event="pull_request"))
    assert not actionable_run(_run(head_branch="genesis/candidate-x"))
    assert not actionable_run(_run(id=99), current_run_id=99)


def test_select_actionable_run_prefers_latest_main_failure():
    selected = select_actionable_run([_run(id=1, updated_at="2026-08-25T09:00:00Z"), _run(id=2, updated_at="2026-08-25T11:00:00Z")])
    assert selected["id"] == 2


def test_failure_fingerprint_is_stable_for_same_workflow_step():
    first = {"workflow_id": 8, "workflow_path": ".github/workflows/a.yml", "failed_job": "build", "failed_step": "test"}
    second = {**first, "run_id": 999, "head_sha": "a" * 40}
    assert failure_fingerprint(first) == failure_fingerprint(second)


def test_sanitize_log_excerpt_redacts_token_like_values():
    text = "Authorization: Bearer ghp_abcdefghijklmnopqrstuvwxyz\napi_key=super-secret-value"
    cleaned = sanitize_log_excerpt(text)
    assert "abcdefghijklmnopqrstuvwxyz" not in cleaned
    assert "super-secret-value" not in cleaned
    assert "REDACTED" in cleaned
