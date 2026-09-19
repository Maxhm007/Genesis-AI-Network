from __future__ import annotations

import argparse
import hashlib
import json
import os
import re

from genesis.issue_lifecycle import family_id, lifecycle_decision, labels
from scripts.issue_lifecycle_reconcile import (
    ACTIVE_LABELS,
    all_issues,
    ensure_label,
    issue_comments,
    post_comment,
    remove_label,
    request,
)

CERT_MARKER = "<!-- genesis-closure-certificate -->"
VERIFIED_LABEL = "genesis-verified"
SEALED_COMPLETED = "genesis-closed-sealed-completed"
SEALED_NOT_PLANNED = "genesis-closed-sealed-not-planned"
SEALED_DUPLICATE = "genesis-closed-sealed-duplicate"
ACTIVE_RESERVATIONS = {
    "genesis-repair-in-progress",
    "genesis-validating",
    "genesis-claimed",
    "genesis-working",
    "genesis-verifying",
}
EVIDENCE_PATTERNS = (
    "genesis verification evidence:",
    "genesis verified and promoted",
    "independently verified this issue",
    "independently validated and promoted",
    "verified repair",
    "full repository validation passed",
    "focused and full repository validation passed",
)
SHA_RE = re.compile(r"\b[0-9a-f]{40}\b", re.IGNORECASE)


def _verification_evidence(comments: list[dict]) -> tuple[bool, str, str]:
    for row in reversed(comments):
        body = str(row.get("body") or "")
        lowered = body.lower()
        if any(pattern in lowered for pattern in EVIDENCE_PATTERNS):
            matches = SHA_RE.findall(body)
            promoted_sha = matches[-1].lower() if matches else ""
            digest = hashlib.sha256(body.encode("utf-8")).hexdigest()[:20]
            return True, digest, promoted_sha
    return False, "", ""


def _certificate(issue: dict, *, reason: str, reference: int | None, evidence_digest: str, promoted_sha: str) -> dict:
    return {
        "schema": "genesis.issue-closure-certificate.v1",
        "issue": int(issue.get("number") or 0),
        "family_id": family_id(issue),
        "closure_reason": reason,
        "reference_issue": reference,
        "verified": VERIFIED_LABEL in labels(issue),
        "evidence_digest": evidence_digest,
        "promoted_sha": promoted_sha,
        "manager_run": os.environ.get("GITHUB_RUN_ID", ""),
    }


def _post_certificate(repository: str, token: str, number: int, certificate: dict) -> None:
    comments = issue_comments(repository, token, number)
    if any(CERT_MARKER in str(row.get("body") or "") for row in comments):
        return
    post_comment(repository, token, number, CERT_MARKER + "\n" + json.dumps(certificate, sort_keys=True))


def _clear_active(repository: str, token: str, number: int) -> None:
    for label in ACTIVE_LABELS:
        remove_label(repository, token, number, label)


def _seal(repository: str, token: str, number: int, seal: str) -> None:
    for label in (SEALED_COMPLETED, SEALED_NOT_PLANNED, SEALED_DUPLICATE):
        if label != seal:
            remove_label(repository, token, number, label)
    request(repository, token, "POST", f"/issues/{number}/labels", {"labels": [seal]})


def reconcile(repository: str, token: str, *, issue_number: int | None = None, max_changes: int = 50) -> dict:
    ensure_label(repository, token, "genesis-superseded", "6e7781", "Closed because current authority shows duplicate or superseded work")
    ensure_label(repository, token, SEALED_COMPLETED, "0e8a16", "Closed after verified Genesis completion evidence")
    ensure_label(repository, token, SEALED_NOT_PLANNED, "6e7781", "Closed by Genesis lifecycle authority as superseded or obsolete")
    ensure_label(repository, token, SEALED_DUPLICATE, "cfd3d7", "Closed by Genesis lifecycle authority as duplicate")

    issues = all_issues(repository, token)
    by_number = {int(row.get("number") or 0): row for row in issues if int(row.get("number") or 0) > 0}
    ordered = [issue_number] if issue_number else sorted(by_number)
    changes: list[dict] = []

    for number in ordered:
        if len(changes) >= max_changes:
            break
        issue = by_number.get(int(number))
        if not issue:
            continue

        state = str(issue.get("state") or "").lower()
        issue_labels = labels(issue)
        comments = issue_comments(repository, token, int(number))
        decision = lifecycle_decision(issue, by_number, comments=comments)

        if state == "open" and decision.action in {"close_superseded", "close_duplicate"}:
            seal = SEALED_DUPLICATE if decision.action == "close_duplicate" else SEALED_NOT_PLANNED
            cert = _certificate(
                issue,
                reason=decision.reason,
                reference=decision.reference_issue,
                evidence_digest="lifecycle-authority",
                promoted_sha="",
            )
            _post_certificate(repository, token, int(number), cert)
            request(repository, token, "PATCH", f"/issues/{number}", {"state": "closed", "state_reason": "not_planned"})
            request(repository, token, "POST", f"/issues/{number}/labels", {"labels": ["genesis-superseded"]})
            _clear_active(repository, token, int(number))
            _seal(repository, token, int(number), seal)
            changes.append({"issue": int(number), "action": decision.action, "reason": decision.reason})
            continue

        if state == "open" and VERIFIED_LABEL in issue_labels:
            if issue_labels & ACTIVE_RESERVATIONS:
                continue
            verified, evidence_digest, promoted_sha = _verification_evidence(comments)
            if not verified:
                continue
            cert = _certificate(
                issue,
                reason="verified_completion",
                reference=None,
                evidence_digest=evidence_digest,
                promoted_sha=promoted_sha,
            )
            _post_certificate(repository, token, int(number), cert)
            request(repository, token, "PATCH", f"/issues/{number}", {"state": "closed", "state_reason": "completed"})
            _clear_active(repository, token, int(number))
            _seal(repository, token, int(number), SEALED_COMPLETED)
            changes.append({"issue": int(number), "action": "close_completed", "reason": "verified_completion"})
            continue

        if state == "closed" and decision.action == "reopen":
            request(repository, token, "PATCH", f"/issues/{number}", {"state": "open"})
            request(repository, token, "POST", f"/issues/{number}/labels", {"labels": ["genesis-autonomous"]})
            post_comment(repository, token, int(number), CERT_MARKER + "\nClosure Manager reopened this authoritative unverified root.")
            changes.append({"issue": int(number), "action": "reopen", "reason": decision.reason})

    return {"status": "ok", "change_count": len(changes), "changes": changes}


def main() -> int:
    parser = argparse.ArgumentParser(description="Genesis authoritative issue closure manager")
    parser.add_argument("--issue-number", type=int)
    parser.add_argument("--max-changes", type=int, default=50)
    args = parser.parse_args()

    repository = os.environ.get("GITHUB_REPOSITORY", "").strip()
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if not repository or not token:
        raise SystemExit("GITHUB_REPOSITORY and GITHUB_TOKEN are required")

    print(json.dumps(reconcile(repository, token, issue_number=args.issue_number, max_changes=args.max_changes), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
