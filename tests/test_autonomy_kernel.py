from datetime import datetime, timedelta, timezone

from genesis.autonomy_kernel import IssueState, decide_issue, issue_state, summarize_issues


NOW = datetime(2026, 10, 25, 0, 0, tzinfo=timezone.utc)


def _issue(number: int, labels=(), minutes_ago: int = 5, state: str = "open") -> dict:
    return {
        "number": number,
        "state": state,
        "labels": [{"name": label} for label in labels],
        "updated_at": (NOW - timedelta(minutes=minutes_ago)).isoformat(),
    }


def test_state_machine_prefers_validation_and_verification_over_ready():
    assert issue_state(_issue(1, ("genesis-autonomous", "genesis-validating"))) is IssueState.VALIDATING
    assert issue_state(_issue(2, ("genesis-autonomous", "genesis-verified"))) is IssueState.VERIFIED


def test_ready_issue_dispatches_solver():
    decision = decide_issue(_issue(3, ("genesis-autonomous",)), now=NOW)
    assert decision.state == "ready"
    assert decision.action == "dispatch_solver"
    assert decision.stalled is False


def test_stalled_ready_issue_requests_materially_new_strategy():
    decision = decide_issue(
        _issue(4, ("genesis-autonomous",), minutes_ago=180),
        now=NOW,
        stalled_minutes=90,
    )
    assert decision.stalled is True
    assert decision.action == "recover_with_new_strategy"


def test_solver_cannot_self_approve_validation():
    decision = decide_issue(
        _issue(5, ("genesis-autonomous", "genesis-validating")),
        now=NOW,
    )
    assert decision.action == "await_independent_validation"


def test_verified_issue_is_reconciled_to_closure():
    decision = decide_issue(
        _issue(6, ("genesis-autonomous", "genesis-verified")),
        now=NOW,
    )
    assert decision.action == "close_verified"


def test_summary_tracks_outcomes_and_human_intervention():
    report = summarize_issues(
        [
            _issue(10, ("genesis-autonomous",)),
            _issue(11, ("genesis-autonomous", "genesis-solver-exhausted"), minutes_ago=200),
            _issue(12, ("genesis-autonomous", "genesis-validating")),
            _issue(13, ("genesis-autonomous", "genesis-verified")),
            _issue(14, ("genesis-autonomous", "genesis-human-required")),
        ],
        now=NOW,
    )
    assert report["ready_issue_numbers"] == [10, 14]
    assert report["recovery_issue_numbers"] == [11]
    assert report["validating_issue_numbers"] == [12]
    assert report["verified_to_close_issue_numbers"] == [13]
    assert report["human_intervention_required_count"] == 1
    assert report["unattended_open_ratio"] == 0.8


def test_monitoring_issue_is_not_solver_work():
    from datetime import datetime, timezone
    from genesis.autonomy_kernel import decide_issue

    now = datetime(2026, 10, 27, 12, 0, tzinfo=timezone.utc)
    issue = {"number": 1100, "state": "open", "updated_at": "2026-10-26T00:00:00Z",
             "title": "[Monitoring] Live Genesis Actions status report",
             "labels": [{"name": "genesis-autonomous"}, {"name": "genesis-solver-exhausted"}, {"name": "agentic-lab"}]}
    assert decide_issue(issue, now=now).action == "none"


def test_exhausted_issue_waits_for_cooldown_before_retry():
    from datetime import datetime, timezone
    from genesis.autonomy_kernel import decide_issue

    now = datetime(2026, 10, 27, 12, 0, tzinfo=timezone.utc)
    labels = [{"name": "genesis-autonomous"}, {"name": "genesis-solver-exhausted"}]
    fresh = {"number": 8, "state": "open", "updated_at": "2026-10-27T11:50:00Z", "labels": labels}
    aged = {"number": 9, "state": "open", "updated_at": "2026-10-27T11:20:00Z", "labels": labels}
    assert decide_issue(fresh, now=now).action == "cooldown"
    assert decide_issue(aged, now=now).action == "recover_with_new_strategy"
