from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from .issue_lifecycle import is_closed, is_verified, root_issue_number


PROBLEM_MARKER = "Genesis-Problem-Fingerprint:"
OCCURRENCE_MARKER = "Genesis-Occurrence-Fingerprint:"

SEVERITY_WEIGHTS = {
    "critical": 1.0,
    "high": 0.8,
    "medium": 0.55,
    "low": 0.3,
}


def _norm(value: object) -> str:
    return " ".join(str(value or "").replace("\\", "/").split()).strip().lower()


def problem_fingerprint(*, target: str, failure_class: str, objective: str) -> str:
    material = {
        "target": _norm(target),
        "failure_class": _norm(failure_class),
        "objective": _norm(objective),
    }
    digest = hashlib.sha256(json.dumps(material, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
    return f"genesis-problem:{digest[:32]}"


def occurrence_fingerprint(
    *,
    target: str,
    failure_class: str,
    objective: str,
    evidence: str,
    source_revision: str = "",
) -> str:
    material = {
        "problem": problem_fingerprint(target=target, failure_class=failure_class, objective=objective),
        "evidence": _norm(evidence),
        "source_revision": _norm(source_revision),
    }
    digest = hashlib.sha256(json.dumps(material, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
    return f"genesis-occurrence:{digest[:32]}"


def extract_marker(body: str, marker: str) -> str:
    match = re.search(rf"^{re.escape(marker)}\s*([^\n]+)$", str(body or ""), re.MULTILINE | re.IGNORECASE)
    return match.group(1).strip().lower() if match else ""


@dataclass(frozen=True)
class IssueValue:
    score: float
    breakdown: dict[str, float]


def issue_value_score(
    *,
    severity: str = "medium",
    blocked_issues: int = 0,
    age_hours: float = 0.0,
    reuse_value: float = 0.5,
    owner_priority: float = 0.0,
    retry_depth: int = 0,
    success_probability: float = 0.7,
) -> IssueValue:
    sev = SEVERITY_WEIGHTS.get(_norm(severity), SEVERITY_WEIGHTS["medium"])
    blocked = min(1.0, max(0.0, float(blocked_issues)) / 8.0)
    age = min(1.0, max(0.0, float(age_hours)) / (24.0 * 14.0))
    reuse = min(1.0, max(0.0, float(reuse_value)))
    owner = min(1.0, max(0.0, float(owner_priority)))
    retries = min(1.0, max(0.0, float(retry_depth)) / 8.0)
    success = min(1.0, max(0.0, float(success_probability)))

    breakdown = {
        "severity": 30.0 * sev,
        "blocked_issues": 20.0 * blocked,
        "age": 18.0 * age,
        "reuse_value": 12.0 * reuse,
        "owner_priority": 12.0 * owner,
        "success_probability": 12.0 * success,
        "retry_penalty": -8.0 * retries,
    }
    score = max(0.0, min(100.0, sum(breakdown.values())))
    return IssueValue(round(score, 3), {key: round(value, 3) for key, value in breakdown.items()})


@dataclass(frozen=True)
class BacklogHealth:
    state: str
    open_count: int
    opened_24h: int
    closed_24h: int
    net_velocity: int


def backlog_health(
    *,
    open_count: int,
    opened_24h: int,
    closed_24h: int,
    healthy_limit: int = 25,
    warning_limit: int = 50,
) -> BacklogHealth:
    open_count = max(0, int(open_count))
    opened_24h = max(0, int(opened_24h))
    closed_24h = max(0, int(closed_24h))
    net = opened_24h - closed_24h
    if open_count >= warning_limit or (open_count >= healthy_limit and net >= 3):
        state = "overloaded"
    elif open_count >= healthy_limit or net > 0:
        state = "warning"
    else:
        state = "healthy"
    return BacklogHealth(state, open_count, opened_24h, closed_24h, net)


def _issue_state(issue: dict) -> str:
    return _norm(issue.get("state"))


def equivalent_issue(
    issues: Iterable[dict],
    *,
    problem_fp: str,
    occurrence_fp: str,
) -> tuple[str, dict | None]:
    entries = list(issues)
    by_number = {
        int(issue.get("number") or 0): issue
        for issue in entries
        if int(issue.get("number") or 0) > 0
    }
    closed_occurrence = None
    for issue in entries:
        body = str(issue.get("body") or "")
        same_problem = extract_marker(body, PROBLEM_MARKER) == _norm(problem_fp)
        same_occurrence = extract_marker(body, OCCURRENCE_MARKER) == _norm(occurrence_fp)

        if same_problem and _issue_state(issue) == "open":
            root_number = root_issue_number(issue)
            if root_number:
                root = by_number.get(root_number)
                if root is not None:
                    if not is_closed(root):
                        return "reuse_open_root", root
                    if not is_verified(root):
                        return "reuse_closed_root", root
                    # A stale successor of a verified root must not suppress a
                    # legitimate fresh post-fix recurrence.
                    continue
            return "reuse_open", issue

        if same_occurrence and _issue_state(issue) == "closed":
            closed_occurrence = issue

    if closed_occurrence is not None:
        return "reuse_closed_occurrence", closed_occurrence
    return "new", None


def publication_decision(
    *,
    health: BacklogHealth,
    value_score: float,
    severity: str,
    bypass_labels: Iterable[str] = (),
) -> str:
    labels = {_norm(item) for item in bypass_labels}
    critical = _norm(severity) == "critical" or bool(
        labels & {"security", "critical", "owner-priority", "owner_priority", "production-down"}
    )
    if critical:
        return "publish"
    if health.state == "overloaded" and value_score < 70.0:
        return "defer"
    if health.state == "warning" and value_score < 45.0:
        return "defer"
    return "publish"


def persist_deferred_candidate(path: Path, candidate: dict) -> int:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    rows: list[dict] = []
    if path.is_file():
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(loaded, list):
                rows = [row for row in loaded if isinstance(row, dict)]
        except (OSError, ValueError):
            rows = []

    occurrence = _norm(candidate.get("occurrence_fingerprint"))
    if occurrence and any(_norm(row.get("occurrence_fingerprint")) == occurrence for row in rows):
        return len(rows)

    row = dict(candidate)
    row.setdefault("deferred_at", datetime.now(timezone.utc).isoformat())
    rows.append(row)
    path.write_text(json.dumps(rows[-500:], indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return len(rows)


def count_recent_velocity(issues: Iterable[dict], *, now: datetime | None = None) -> tuple[int, int, int]:
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    cutoff = now.timestamp() - 86400
    open_count = 0
    opened = 0
    closed = 0
    for issue in issues:
        if _issue_state(issue) == "open":
            open_count += 1
        created = str(issue.get("createdAt") or issue.get("created_at") or "")
        closed_at = str(issue.get("closedAt") or issue.get("closed_at") or "")
        for value, kind in ((created, "opened"), (closed_at, "closed")):
            if not value:
                continue
            try:
                dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError:
                continue
            if dt.timestamp() >= cutoff:
                if kind == "opened":
                    opened += 1
                else:
                    closed += 1
    return open_count, opened, closed
