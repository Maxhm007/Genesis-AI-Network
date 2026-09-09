from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request

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


def prioritize(repository: str, token: str) -> dict:
    issues = capability_issues(repository, token)
    if not issues:
        return {"status": "idle", "reason": "no_open_capability_issue"}

    current_generation = engine_generation()
    eligible: list[dict] = []
    quarantined: list[int] = []

    # Never reactivate capability work quarantined for the current repair-engine
    # generation.  It becomes eligible only after engine_generation() changes,
    # which prevents the priority scheduler from recycling the same exhausted
    # Issue indefinitely.
    for issue in issues:
        number = int(issue.get("number") or 0)
        comments = issue_comments(repository, token, number)
        if quarantined_for_current_generation(comments, current_generation):
            quarantined.append(number)
            continue
        eligible.append(issue)

    if not eligible:
        return {
            "status": "idle",
            "reason": "all_capability_issues_quarantined_for_current_generation",
            "repair_engine_generation": current_generation,
            "quarantined": quarantined,
        }

    # Only eligible capability work is made visible to Agentic Lab. Oldest
    # eligible issue wins; quarantined issues are skipped so the queue advances.
    for issue in eligible:
        number = int(issue.get("number") or 0)
        issue_labels = labels(issue)
        missing = [
            label
            for label in ("genesis-task", "genesis-repair", "genesis-autonomous", AGENTIC_LABEL)
            if label not in issue_labels
        ]
        if missing:
            request(repository, token, "POST", f"/issues/{number}/labels", {"labels": missing})

    oldest = eligible[0]
    oldest_number = int(oldest.get("number") or 0)
    oldest_labels = labels(oldest)
    if not (oldest_labels & ACTIVE_LABELS):
        request(
            repository,
            token,
            "POST",
            "/actions/workflows/genesis-agentic-lab-recovery.yml/dispatches",
            {"ref": "main"},
        )

    return {
        "status": "prioritized",
        "oldest_capability_issue": oldest_number,
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
