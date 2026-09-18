from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from datetime import datetime, timezone

from genesis.issue_governor import issue_value_score
from requeue_exhausted_issues import engine_generation

CAPABILITY_WORK_PREFIX = "<!-- genesis-capability-work:"
REQUEUE_MARKER_PREFIX = "<!-- genesis-requeue-engine:"
AGENTIC_LABEL = "agentic-lab"
ACTIVE_LABELS = {
    "genesis-repair-in-progress",
    "genesis-validating",
    "genesis-working",
    "genesis-verifying",
}


def request(repository: str, token: str, method: str, path: str, payload: dict | None = None):
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
            "User-Agent": "Genesis-AI-Network/capability-priority",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            raw = response.read().decode("utf-8")
        return json.loads(raw) if raw.strip() else {}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:1000]
        raise RuntimeError(f"GitHub HTTP {exc.code} for {method} {path}: {detail}") from exc


def labels(issue: dict) -> set[str]:
    result: set[str] = set()
    for row in issue.get("labels") or []:
        name = str(row.get("name") if isinstance(row, dict) else row or "").strip()
        if name:
            result.add(name)
    return result


def open_issues(repository: str, token: str) -> list[dict]:
    rows: list[dict] = []
    for page in range(1, 101):
        batch = request(
            repository,
            token,
            "GET",
            f"/issues?state=open&sort=created&direction=asc&per_page=100&page={page}",
        )
        if not isinstance(batch, list):
            raise RuntimeError("GitHub open issue response was not a list")
        rows.extend(row for row in batch if isinstance(row, dict) and not row.get("pull_request"))
        if len(batch) < 100:
            break
    return rows


def issue_comments(repository: str, token: str, number: int) -> list[dict]:
    rows = request(repository, token, "GET", f"/issues/{number}/comments?per_page=100") or []
    return [row for row in rows if isinstance(row, dict)]


def latest_requeue_marker(comments: list[dict]) -> tuple[str, str]:
    generation = ""
    body = ""
    pattern = re.compile(re.escape(REQUEUE_MARKER_PREFIX) + r"([^\s]+)\s*-->")
    for row in comments:
        text = str(row.get("body") or "")
        match = pattern.search(text)
        if match:
            generation = match.group(1).strip()
            body = text
    return generation, body


def quarantined_for_current_generation(comments: list[dict], current_generation: str) -> bool:
    marker_generation, marker_body = latest_requeue_marker(comments)
    if not marker_generation or marker_generation != current_generation:
        return False
    text = marker_body.lower()
    return (
        "quarantined for this repair-engine generation" in text
        or "terminally deferred" in text
    )


def capability_issues(repository: str, token: str) -> list[dict]:
    return [
        issue
        for issue in open_issues(repository, token)
        if CAPABILITY_WORK_PREFIX in str(issue.get("body") or "")
        and "genesis-verified" not in labels(issue)
    ]


def _severity(issue_labels: set[str]) -> str:
    lowered = {label.lower() for label in issue_labels}
    if lowered & {"critical", "severity-critical", "security-critical"}:
        return "critical"
    if lowered & {"high", "severity-high", "priority-high"}:
        return "high"
    if lowered & {"low", "severity-low", "priority-low"}:
        return "low"
    return "medium"


def _age_hours(issue: dict, now: datetime) -> float:
    raw = str(issue.get("created_at") or issue.get("createdAt") or "")
    try:
        created = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return 0.0
    if created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    return max(0.0, (now - created.astimezone(timezone.utc)).total_seconds() / 3600.0)


def _blocked_issue_count(issue: dict) -> int:
    body = str(issue.get("body") or "")
    explicit = re.findall(r"(?i)\b(?:blocks?|unlocks?)\s+#(\d+)\b", body)
    return len(set(explicit))


def _retry_depth(comments: list[dict]) -> int:
    markers = 0
    for row in comments:
        text = str(row.get("body") or "").lower()
        if "genesis-requeue-engine:" in text or "repair attempt" in text or "retry" in text:
            markers += 1
    return markers


def score_issue(issue: dict, comments: list[dict], *, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    issue_labels = labels(issue)
    retry_depth = _retry_depth(comments)
    owner_priority = 1.0 if issue_labels & {"owner-priority", "owner_priority", "user-priority"} else 0.0
    reuse_value = 0.9 if issue_labels & {"genesis-capability", "genesis-capability-blocker", "capability-blocker"} else 0.7
    success_probability = max(0.25, 0.88 - 0.08 * retry_depth)
    value = issue_value_score(
        severity=_severity(issue_labels),
        blocked_issues=_blocked_issue_count(issue),
        age_hours=_age_hours(issue, now),
        reuse_value=reuse_value,
        owner_priority=owner_priority,
        retry_depth=retry_depth,
        success_probability=success_probability,
    )
    return {
        "number": int(issue.get("number") or 0),
        "score": value.score,
        "breakdown": value.breakdown,
        "retry_depth": retry_depth,
        "blocked_issues": _blocked_issue_count(issue),
    }


def prioritize(repository: str, token: str) -> dict:
    issues = capability_issues(repository, token)
    if not issues:
        return {"status": "idle", "reason": "no_open_capability_issue"}

    current_generation = engine_generation()
    eligible: list[tuple[dict, list[dict]]] = []
    quarantined: list[int] = []

    for issue in issues:
        number = int(issue.get("number") or 0)
        comments = issue_comments(repository, token, number)
        if quarantined_for_current_generation(comments, current_generation):
            quarantined.append(number)
            continue
        eligible.append((issue, comments))

    if not eligible:
        return {
            "status": "idle",
            "reason": "all_capability_issues_quarantined_for_current_generation",
            "repair_engine_generation": current_generation,
            "quarantined": quarantined,
        }

    for issue, _comments in eligible:
        number = int(issue.get("number") or 0)
        issue_labels = labels(issue)
        missing = [
            label
            for label in ("genesis-task", "genesis-repair", "genesis-autonomous", AGENTIC_LABEL)
            if label not in issue_labels
        ]
        if missing:
            request(repository, token, "POST", f"/issues/{number}/labels", {"labels": missing})

    now = datetime.now(timezone.utc)
    scored = [(issue, score_issue(issue, comments, now=now)) for issue, comments in eligible]
    scored.sort(
        key=lambda row: (
            -float(row[1]["score"]),
            str(row[0].get("created_at") or row[0].get("createdAt") or ""),
            int(row[0].get("number") or 0),
        )
    )
    selected, decision = scored[0]
    selected_number = int(selected.get("number") or 0)
    selected_labels = labels(selected)
    if not (selected_labels & ACTIVE_LABELS):
        request(
            repository,
            token,
            "POST",
            "/actions/workflows/genesis-agentic-lab-recovery.yml/dispatches",
            {"ref": "main"},
        )

    return {
        "status": "prioritized",
        "selected_capability_issue": selected_number,
        # Compatibility field retained for downstream readers; it now identifies
        # the selected highest-value safe issue rather than blindly the oldest.
        "oldest_capability_issue": selected_number,
        "selected_value_score": decision["score"],
        "selected_value_breakdown": decision["breakdown"],
        "ranked_candidates": [row[1] for row in scored[:10]],
        "open_capability_issues": len(issues),
        "eligible_capability_issues": len(eligible),
        "quarantined_capability_issues": quarantined,
        "repair_engine_generation": current_generation,
    }


def main() -> int:
    repository = os.environ.get("GITHUB_REPOSITORY", "").strip()
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if not repository or not token:
        raise SystemExit("GITHUB_REPOSITORY and GITHUB_TOKEN are required")
    print(json.dumps(prioritize(repository, token), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
