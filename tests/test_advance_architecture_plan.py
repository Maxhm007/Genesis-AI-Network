from scripts.advance_architecture_plan import advance_body


def test_non_architecture_issue_is_complete():
    status, body = advance_body("plain issue", "genesis/example.py")
    assert status == "complete"
    assert body == "plain issue"


def test_architecture_plan_advances_to_next_target():
    body = (
        "<!-- genesis-architecture-plan:abc -->\n"
        "- **Architecture step:** `1/2`\n"
        "- **Architecture reason:** `pull_request_maintenance`\n"
        "- **Task type:** `architecture_expansion`\n"
        "- **Architecture new target:** `genesis/architecture_extensions/pull_request_maintenance.py`\n"
        "- **Architecture next target:** `genesis/github_issue_cleanup.py`\n"
        "- **Target:** `genesis/architecture_extensions/pull_request_maintenance.py`\n"
    )
    status, updated = advance_body(
        body,
        "genesis/architecture_extensions/pull_request_maintenance.py",
    )
    assert status == "continued"
    assert "- **Architecture step:** `2/2`" in updated
    assert "- **Target:** `genesis/github_issue_cleanup.py`" in updated
    assert "Architecture next target" not in updated
    assert "Architecture new target" not in updated
    assert "architecture_expansion" not in updated


def test_final_architecture_step_completes():
    body = (
        "<!-- genesis-architecture-plan:abc -->\n"
        "- **Architecture step:** `2/2`\n"
        "- **Target:** `genesis/github_issue_cleanup.py`\n"
    )
    status, updated = advance_body(body, "genesis/github_issue_cleanup.py")
    assert status == "complete"
    assert updated == body


def test_completed_target_must_match_current_plan():
    body = (
        "<!-- genesis-architecture-plan:abc -->\n"
        "- **Architecture step:** `1/2`\n"
        "- **Architecture next target:** `genesis/github_issue_cleanup.py`\n"
        "- **Target:** `genesis/architecture_extensions/pull_request_maintenance.py`\n"
    )
    try:
        advance_body(body, "genesis/other.py")
    except ValueError as exc:
        assert "does not match" in str(exc)
    else:
        raise AssertionError("expected mismatch rejection")
