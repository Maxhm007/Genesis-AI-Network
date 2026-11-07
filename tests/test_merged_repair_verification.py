from __future__ import annotations

import json

import pytest

from scripts import issue_closure_manager as closure
from scripts.verify_merged_issue_repair import validate_merged_repair

SHA = "587074e8a740e3c158066edb778852e268cd2025"
ISSUE = {
    "number": 381,
    "state": "open",
    "labels": [{"name": "genesis-task"}, {"name": "agentic-lab"}, {"name": "genesis-solver-exhausted"}],
    "body": "- **Target:** `genesis/immortality_scan.py`",
}
PR = {
    "number": 1159,
    "merged_at": "2026-11-07T20:33:47Z",
    "merge_commit_sha": SHA,
    "base": {"ref": "main"},
    "title": "Fix #381 scanner error isolation",
    "body": "Fixes #381",
}
FILES = [
    {"filename": "genesis/immortality_scan.py"},
    {"filename": "tests/test_immortality_scan.py"},
    {"filename": ".github/workflows/genesis-repair-checkpoint-gate.yml"},
]


def test_exact_scoped_merged_repair_is_eligible_for_independent_verification():
    assert validate_merged_repair(ISSUE, PR, FILES, number=381, pr_number=1159, sha=SHA) == "genesis/immortality_scan.py"


@pytest.mark.parametrize("field,patch", [
    ("sha", {"sha": "f" * 40}),
    ("pr", {"pr": {**PR, "merged_at": None}}),
    ("pr", {"pr": {**PR, "base": {"ref": "feature"}}}),
    ("pr", {"pr": {**PR, "title": "Fix #38", "body": ""}}),
    ("files", {"files": FILES + [{"filename": ".github/workflows/secret-guard.yml"}]}),
    ("files", {"files": FILES[:1]}),
    ("issue", {"issue": {**ISSUE, "labels": [{"name": "genesis-owner-paused"}]}}),
]):
def test_rejects_unverified_or_out_of_scope_merges(field, patch):
    params = {"issue": ISSUE, "pr": PR, "changed_files": FILES, "number": 381, "pr_number": 1159, "sha": SHA}
    params.update(patch)
    if "files" in params:
        params["changed_files"] = params.pop("files")
    with pytest.raises(ValueError):
        validate_merged_repair(**params)


def test_reopen_notice_does_not_suppress_real_certificate(monkeypatch):
    history = [{"body": "<!-- genesis-closure-certificate -->\nClosure Manager reopened this authoritative unverified root."}]
    posted = []
    monkeypatch.setattr(closure, "issue_comments", lambda *args: history)
    monkeypatch.setattr(closure, "post_comment", lambda *args: posted.append(args[3]))
    cert = {
        "schema": "genesis.issue-closure-certificate.v1",
        "issue": 381,
        "closure_reason": "verified_completion",
        "verified": True,
        "promoted_sha": SHA,
    }
    closure._post_certificate("owner/repo", "token", 381, cert)
    assert len(posted) == 1
    assert json.loads(posted[0].split("\n", 1)[1])["promoted_sha"] == SHA


def test_matching_certificate_is_idempotent(monkeypatch):
    cert = {
        "schema": "genesis.issue-closure-certificate.v1",
        "issue": 381,
        "closure_reason": "verified_completion",
        "verified": True,
        "promoted_sha": SHA,
    }
    history = [{"body": "<!-- genesis-closure-certificate -->\n" + json.dumps(cert)}]
    monkeypatch.setattr(closure, "issue_comments", lambda *args: history)
    monkeypatch.setattr(closure, "post_comment", lambda *args: (_ for _ in ()).throw(AssertionError("duplicate seal")))
    closure._post_certificate("owner/repo", "token", 381, cert)
