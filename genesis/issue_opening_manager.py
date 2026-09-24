from __future__ import annotations

import hashlib
import json
import os
import re
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable

LANE_MARKER = "Genesis-Opening-Lane:"
MANAGER_MARKER = "<!-- genesis-issue-opening-manager -->"
AGENTIC_AUTHORITY_MARKER = "<!-- genesis-agentic-opening-authority -->"
AGENTIC_CANDIDATE_EVENT = "genesis-issue-candidate"


def _norm(value: object) -> str:
    return " ".join(str(value or "").replace("\\", "/").split()).strip().lower()


def _tokens(value: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9_./+-]{3,}", _norm(value))
        if token not in {"genesis", "issue", "task", "new", "open", "opened", "the", "and", "for", "with"}
    }


def _similarity(left: str, right: str) -> float:
    a, b = _tokens(left), _tokens(right)
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _target(body: str) -> str:
    patterns = (
        r"(?im)^- \*\*Target:\*\* `([^`]+)`",
        r"(?im)^Target:\s*`([^`]+)`",
        r"(?im)^- \*\*Integration target:\*\* `([^`]+)`",
    )
    for pattern in patterns:
        match = re.search(pattern, str(body or ""))
        if match:
            return _norm(match.group(1))
    return ""


def _marker(body: str, name: str) -> str:
    match = re.search(rf"(?im)^{re.escape(name)}\s*([^\n]+)", str(body or ""))
    return _norm(match.group(1)) if match else ""


def annotate_body(body: str, lane: str) -> str:
    text = str(body or "").rstrip()
    if MANAGER_MARKER in text:
        return text + "\n"
    return (
        f"{MANAGER_MARKER}\n"
        f"{LANE_MARKER} {lane}\n"
        f"{text}\n"
    )


@dataclass(frozen=True)
class OpeningDecision:
    action: str
    reason: str
    lane: str
    duplicate_issue_number: int | None = None
    duplicate_issue_url: str | None = None
    open_count: int = 0
    opened_24h: int = 0
    closed_24h: int = 0


def _parse_time(value: object) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def _counts(issues: Iterable[dict], now: datetime | None = None) -> tuple[int, int, int]:
    now = now or datetime.now(timezone.utc)
    cutoff = now.timestamp() - 86400
    opened = closed = open_count = 0
    for issue in issues:
        state = _norm(issue.get("state"))
        if state == "open":
            open_count += 1
        created = _parse_time(issue.get("createdAt") or issue.get("created_at"))
        closed_at = _parse_time(issue.get("closedAt") or issue.get("closed_at"))
        if created and created.timestamp() >= cutoff:
            opened += 1
        if closed_at and closed_at.timestamp() >= cutoff:
            closed += 1
    return open_count, opened, closed


def decide(
    *,
    lane: str,
    title: str,
    body: str,
    issues: Iterable[dict],
    severity: str = "medium",
    value_score: float = 60.0,
    bypass_backlog: bool = False,
) -> OpeningDecision:
    rows = [row for row in issues if isinstance(row, dict) and "pull_request" not in row]
    open_count, opened_24h, closed_24h = _counts(rows)
    candidate_target = _target(body)
    candidate_problem = _marker(body, "Genesis-Problem-Fingerprint:")
    candidate_occurrence = _marker(body, "Genesis-Occurrence-Fingerprint:")
    candidate_corpus = f"{title}\n{body}"

    for issue in rows:
        if _norm(issue.get("state")) != "open":
            continue
        existing_body = str(issue.get("body") or "")
        same_problem = bool(candidate_problem and candidate_problem == _marker(existing_body, "Genesis-Problem-Fingerprint:"))
        same_occurrence = bool(candidate_occurrence and candidate_occurrence == _marker(existing_body, "Genesis-Occurrence-Fingerprint:"))
        same_target = bool(candidate_target and candidate_target == _target(existing_body))
        similarity = _similarity(candidate_corpus, f"{issue.get('title') or ''}\n{existing_body}")

        if same_problem or same_occurrence or (same_target and similarity >= 0.42) or similarity >= 0.72:
            return OpeningDecision(
                "duplicate",
                "equivalent open issue already exists",
                lane,
                int(issue.get("number") or 0) or None,
                str(issue.get("url") or issue.get("html_url") or "") or None,
                open_count,
                opened_24h,
                closed_24h,
            )

    if bypass_backlog or _norm(severity) == "critical":
        return OpeningDecision("publish", "critical/bypass lane", lane, open_count=open_count, opened_24h=opened_24h, closed_24h=closed_24h)

    healthy_limit = int(os.environ.get("GENESIS_ISSUE_HEALTHY_LIMIT", "25"))
    warning_limit = int(os.environ.get("GENESIS_ISSUE_WARNING_LIMIT", "50"))
    net = opened_24h - closed_24h
    overloaded = open_count >= warning_limit or (open_count >= healthy_limit and net >= 3)
    warning = open_count >= healthy_limit or net > 0

    if overloaded and float(value_score) < 70:
        return OpeningDecision("defer", "shared backlog overloaded", lane, open_count=open_count, opened_24h=opened_24h, closed_24h=closed_24h)
    if warning and float(value_score) < 45:
        return OpeningDecision("defer", "shared backlog warning", lane, open_count=open_count, opened_24h=opened_24h, closed_24h=closed_24h)
    return OpeningDecision("publish", "admitted by shared opening policy", lane, open_count=open_count, opened_24h=opened_24h, closed_24h=closed_24h)


def fetch_issues(repository: str, token: str, *, limit: int = 300) -> list[dict]:
    rows: list[dict] = []
    pages = max(1, min(10, (limit + 99) // 100))
    for page in range(1, pages + 1):
        query = urllib.parse.urlencode({"state": "all", "per_page": 100, "page": page, "sort": "created", "direction": "desc"})
        request = urllib.request.Request(
            f"https://api.github.com/repos/{repository}/issues?{query}",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "Genesis-AI-Network/issue-opening-manager",
            },
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            page_rows = json.loads(response.read().decode("utf-8"))
        if not isinstance(page_rows, list):
            break
        rows.extend(row for row in page_rows if isinstance(row, dict))
        if len(page_rows) < 100:
            break
    return rows[:limit]


def gate_remote(
    repository: str,
    token: str,
    *,
    lane: str,
    title: str,
    body: str,
    severity: str = "medium",
    value_score: float = 60.0,
    bypass_backlog: bool = False,
) -> OpeningDecision:
    return decide(
        lane=lane,
        title=title,
        body=body,
        issues=fetch_issues(repository, token),
        severity=severity,
        value_score=value_score,
        bypass_backlog=bypass_backlog,
    )


def fingerprint(lane: str, title: str, body: str) -> str:
    material = f"{_norm(lane)}\n{_norm(title)}\n{_target(body)}\n{_marker(body, 'Genesis-Problem-Fingerprint:')}"
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:20]


def build_agentic_candidate(
    *,
    lane: str,
    title: str,
    body: str,
    labels: Iterable[str] = (),
    severity: str = "medium",
    value_score: float = 60.0,
    bypass_backlog: bool = False,
) -> dict:
    lane = _norm(lane)
    if not re.fullmatch(r"[a-z0-9._-]{1,80}", lane):
        raise ValueError("invalid issue-opening lane")
    title = str(title or "").strip()
    body = str(body or "").strip()
    if not title or len(title) > 240:
        raise ValueError("candidate title must be 1..240 characters")
    if not body or len(body.encode("utf-8")) > 60_000:
        raise ValueError("candidate body must be non-empty and <= 60000 bytes")
    clean_labels: list[str] = []
    for raw in labels:
        label = str(raw or "").strip()
        if not label or len(label) > 100 or label in clean_labels:
            continue
        clean_labels.append(label)
        if len(clean_labels) >= 20:
            break
    return {
        "schema": "genesis.agentic-issue-candidate.v1",
        "lane": lane,
        "title": title,
        "body": body,
        "labels": clean_labels,
        "severity": _norm(severity) or "medium",
        "value_score": max(0.0, min(100.0, float(value_score))),
        "bypass_backlog": bool(bypass_backlog),
        "candidate_fingerprint": fingerprint(lane, title, body),
    }


def submit_agentic_candidate(
    repository: str,
    token: str,
    *,
    lane: str,
    title: str,
    body: str,
    labels: Iterable[str] = (),
    severity: str = "medium",
    value_score: float = 60.0,
    bypass_backlog: bool = False,
) -> OpeningDecision:
    """Submit one validated candidate to Agentic Lab's sole opening authority.

    Discovery lanes remain evidence producers. They do not decide publication and
    they do not create GitHub Issues directly. The repository_dispatch event is
    intentionally the only handoff from producer workflows to the central opener.
    """
    if not repository or not token:
        raise ValueError("repository and token are required")
    candidate = build_agentic_candidate(
        lane=lane,
        title=title,
        body=body,
        labels=labels,
        severity=severity,
        value_score=value_score,
        bypass_backlog=bypass_backlog,
    )
    lane = candidate["lane"]
    payload = {
        "ref": "main",
        "inputs": {"candidate_json": json.dumps(candidate, separators=(",", ":"))},
    }
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        f"https://api.github.com/repos/{repository}/actions/workflows/genesis-agentic-issue-opening.yml/dispatches",
        data=data,
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "Content-Type": "application/json",
            "User-Agent": "Genesis-AI-Network/agentic-issue-candidate",
        },
    )
    with urllib.request.urlopen(request, timeout=30):
        pass
    return OpeningDecision(
        "agentic_pending",
        "delegated to Agentic Lab opening authority",
        lane,
    )
