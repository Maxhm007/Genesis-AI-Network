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
