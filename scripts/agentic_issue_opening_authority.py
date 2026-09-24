from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

from genesis.issue_opening_manager import (
    AGENTIC_AUTHORITY_MARKER,
    annotate_body,
    decide,
    fetch_issues,
)
from genesis.issue_governor import OCCURRENCE_MARKER, PROBLEM_MARKER, extract_marker
from genesis.issue_lifecycle import is_sealed, is_superseded, is_verified


def _request(repository: str, token: str, method: str, path: str, payload: dict | None = None):
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"https://api.github.com/repos/{repository}{path}",
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "Content-Type": "application/json",
            "User-Agent": "Genesis-AI-Network/agentic-issue-opening-authority",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            raw = response.read().decode("utf-8")
        return json.loads(raw) if raw.strip() else {}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:1000]
        raise RuntimeError(f"GitHub HTTP {exc.code} for {method} {path}: {detail}") from exc


def normalize_candidate(payload: dict) -> dict:
    if str(payload.get("schema") or "") != "genesis.agentic-issue-candidate.v1":
        raise ValueError("unsupported candidate schema")
    lane = str(payload.get("lane") or "").strip().lower()
    title = str(payload.get("title") or "").strip()
    body = str(payload.get("body") or "").strip()
    if not lane or not title or not body:
        raise ValueError("candidate lane, title and body are required")
    labels: list[str] = []
    for raw in payload.get("labels") or []:
        label = str(raw or "").strip()
        if label and label not in labels:
            labels.append(label)
        if len(labels) >= 20:
            break
    for required in ("genesis-autonomous", "agentic-lab"):
        if required not in labels:
            labels.append(required)
    return {
        "lane": lane,
        "title": title[:240],
        "body": body,
        "labels": labels,
        "severity": str(payload.get("severity") or "medium").strip().lower(),
        "value_score": max(0.0, min(100.0, float(payload.get("value_score") or 60.0))),
        "bypass_backlog": bool(payload.get("bypass_backlog")),
        "candidate_fingerprint": str(payload.get("candidate_fingerprint") or "").strip(),
    }


def run(repository: str, token: str, payload: dict) -> dict:
    candidate = normalize_candidate(payload)
    issues = fetch_issues(repository, token, limit=500)
    body = candidate["body"]

    problem_fp = extract_marker(body, PROBLEM_MARKER)
    occurrence_fp = extract_marker(body, OCCURRENCE_MARKER)
    if problem_fp and not occurrence_fp:
        for issue in issues:
            if str(issue.get("state") or "").lower() != "closed":
                continue
            existing_problem = extract_marker(str(issue.get("body") or ""), PROBLEM_MARKER)
            if existing_problem != problem_fp:
                continue
            if is_verified(issue) or is_superseded(issue) or is_sealed(issue):
                return {
                    "status": "closed_equivalent",
                    "reason": "same problem already terminal; producer supplied no fresh occurrence fingerprint",
                    "issue_number": int(issue.get("number") or 0) or None,
                    "issue_url": str(issue.get("html_url") or issue.get("url") or "") or None,
                    "lane": candidate["lane"],
                }

    if AGENTIC_AUTHORITY_MARKER not in body:
        body = f"{AGENTIC_AUTHORITY_MARKER}\n{body}"
    decision = decide(
        lane=candidate["lane"],
        title=candidate["title"],
        body=body,
        issues=issues,
        severity=candidate["severity"],
        value_score=candidate["value_score"],
        bypass_backlog=candidate["bypass_backlog"],
    )
    if decision.action == "duplicate":
        return {
            "status": "duplicate",
            "reason": decision.reason,
            "issue_number": decision.duplicate_issue_number,
            "issue_url": decision.duplicate_issue_url,
            "lane": candidate["lane"],
        }
    if decision.action == "defer":
        return {
            "status": "deferred",
            "reason": decision.reason,
            "lane": candidate["lane"],
            "open_count": decision.open_count,
            "opened_24h": decision.opened_24h,
            "closed_24h": decision.closed_24h,
        }

    created = _request(
        repository,
        token,
        "POST",
        "/issues",
        {
            "title": candidate["title"],
            "body": body,
            "labels": candidate["labels"],
        },
    )
    number = int(created.get("number") or 0) if isinstance(created, dict) else 0
    if number <= 0:
        raise RuntimeError("Agentic opening authority did not receive a valid created issue")

    try:
        _request(
            repository,
            token,
            "POST",
            "/actions/workflows/genesis-agentic-lab-recovery.yml/dispatches",
            {"ref": "main"},
        )
    except Exception:
        pass

    return {
        "status": "opened",
        "issue_number": number,
        "issue_url": str(created.get("html_url") or ""),
        "lane": candidate["lane"],
        "candidate_fingerprint": candidate["candidate_fingerprint"],
    }


def main() -> int:
    repository = os.environ.get("GITHUB_REPOSITORY", "").strip()
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    raw = os.environ.get("GENESIS_ISSUE_CANDIDATE", "").strip()
    if not repository or not token or not raw:
        raise SystemExit("GITHUB_REPOSITORY, GITHUB_TOKEN and GENESIS_ISSUE_CANDIDATE are required")
    payload = json.loads(raw)
    result = run(repository, token, payload)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
