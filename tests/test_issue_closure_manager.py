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
