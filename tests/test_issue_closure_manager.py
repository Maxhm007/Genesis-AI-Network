import scripts.issue_closure_manager as module
from scripts.issue_closure_manager import (
    CERT_MARKER,
    EVIDENCE_PATTERNS,
    _certificate,
    _verification_evidence,
)


def _issue(number=10, labels=("genesis-task", "genesis-verified")):
    return {
        "number": number,
        "labels": [{"name": label} for label in labels],
        "body": "",
    }


def test_verification_evidence_accepts_verified_worker_comment():
    ok, digest, promoted = _verification_evidence([
        {
            "body": (
                "Genesis verified and promoted a bounded repair. "
                "Promoted main SHA: 0123456789abcdef0123456789abcdef01234567. "
                "Full repository validation passed after promotion."
            )
        }
    ])
    assert ok is True
    assert len(digest) == 20
    assert promoted == "0123456789abcdef0123456789abcdef01234567"


def test_verification_evidence_rejects_generic_comment():
    ok, digest, promoted = _verification_evidence([{"body": "solver attempted a repair"}])
    assert ok is False
    assert digest == ""
    assert promoted == ""


def test_certificate_is_machine_readable_and_verified():
    cert = _certificate(
        _issue(),
        reason="verified_completion",
        reference=None,
        evidence_digest="abc123",
        promoted_sha="0123456789abcdef0123456789abcdef01234567",
    )
    assert cert["schema"] == "genesis.issue-closure-certificate.v1"
    assert cert["issue"] == 10
    assert cert["verified"] is True
    assert cert["closure_reason"] == "verified_completion"


def test_certificate_marker_is_stable():
    assert CERT_MARKER == "<!-- genesis-closure-certificate -->"
    assert "full repository validation passed" in EVIDENCE_PATTERNS


def test_single_verified_issue_closes_without_full_backlog_scan(monkeypatch):
    issue = {
        "number": 1039,
        "state": "open",
        "labels": [{"name": "genesis-verified"}],
        "body": "",
    }
    calls: list[tuple[str, str]] = []

    def fake_request(repository, token, method, path, payload=None):
        calls.append((method, path))
        if method == "GET" and path == "/issues/1039":
            return issue
        return {}

    monkeypatch.setattr(module, "request", fake_request)
    monkeypatch.setattr(
        module,
        "issue_comments",
        lambda repository, token, number: [{"body": "Genesis verification evidence: full repository validation passed."}],
    )
    monkeypatch.setattr(module, "all_issues", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("full backlog scan used")))
    monkeypatch.setattr(module, "ensure_label", lambda *args, **kwargs: None)
    monkeypatch.setattr(module, "_post_certificate", lambda *args, **kwargs: None)
    monkeypatch.setattr(module, "_clear_active", lambda *args, **kwargs: None)
    monkeypatch.setattr(module, "_seal", lambda *args, **kwargs: None)

    result = module.reconcile("owner/repo", "token", issue_number=1039)

    assert result["change_count"] == 1
    assert result["changes"][0]["action"] == "close_completed"
    assert ("PATCH", "/issues/1039") in calls


def test_verification_must_be_after_latest_problem_comment():
    comments = [
        {"body": "Genesis verification evidence: full repository validation passed."},
        {"body": "<!-- genesis-team-current-problem -->\nprovider_timeout remains unresolved"},
    ]
    verified, _, _ = module._verification_evidence(comments)
    assert verified is False


def test_new_verification_after_problem_comment_is_accepted():
    comments = [
        {"body": "<!-- genesis-team-current-problem -->\nprovider_timeout remains unresolved"},
        {"body": "Genesis verification evidence: full repository validation passed."},
    ]
    verified, _, _ = module._verification_evidence(comments)
    assert verified is True


def test_verified_result_with_completed_status_and_stale_decline_still_closes():
    sha = "5fccf2d63d58c97c0bcb73b3b53e87169a1b2c3d"
    comments = [
        {"body": "Agentic Lab strategy `x` did not produce a verified promotion. repair status: `strategy_requires_more_methods`."},
        {"body": f"<!-- genesis-agentic-strategy-result:evidence_first --> Agentic Lab strategy `evidence_first` produced a verified repair. Promoted main SHA: `{sha}`. repair status: `completed`."},
        {"body": "<!-- genesis-agentic-strategy-result:evidence_first --> Agentic Lab strategy worker declined this reservation because the Issue is not open/owned. repair status: `blocked_protected_or_unsupported_target`."},
    ]
    ok, _, promoted = _verification_evidence(comments)
    assert ok is True
    assert promoted == sha


def test_real_failure_after_verified_result_still_blocks_close():
    comments = [
        {"body": "Agentic Lab strategy produced a verified repair. repair status: `completed`."},
        {"body": "Agentic Lab strategy did not produce a verified promotion. repair status: `tests_failed`."},
    ]
    ok, _, _ = _verification_evidence(comments)
    assert ok is False


_SUCCESS = "<!-- genesis-agentic-strategy-result:evidence_first --> Agentic Lab strategy `evidence_first` produced a verified repair. repair status: `completed`."
_DECLINE = "<!-- genesis-agentic-strategy-result:evidence_first --> Agentic Lab strategy worker declined this reservation because the Issue is not open/owned. repair status: `blocked_protected_or_unsupported_target`."


def test_current_problem_quoting_decline_note_blocks_close():
    comments = [{"body": _SUCCESS}, {"body": "<!-- genesis-team-current-problem --> Still broken. Quoted: " + _DECLINE}]
    assert _verification_evidence(comments)[0] is False


def test_current_problem_quoting_success_blocks_close():
    comments = [{"body": _SUCCESS}, {"body": "<!-- genesis-team-current-problem --> Regressed after: " + _SUCCESS}]
    assert _verification_evidence(comments)[0] is False


def test_decline_note_with_failure_blocks_close():
    comments = [{"body": _SUCCESS}, {"body": _DECLINE + " Worker failed: provider_timeout."}]
    assert _verification_evidence(comments)[0] is False


def test_decline_note_before_any_success_still_counts_as_problem():
    comments = [{"body": _DECLINE}, {"body": "Genesis verification evidence: ok"}]
    assert _verification_evidence(comments)[0] is True
    comments = [{"body": _DECLINE}]
    assert _verification_evidence(comments)[0] is False
