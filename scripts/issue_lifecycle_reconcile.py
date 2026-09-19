from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request

from genesis.issue_lifecycle import family_id, lifecycle_decision


ACTIVE_LABELS = (
    "genesis-repair-in-progress",
    "genesis-validating",
    "genesis-claimed",
    "genesis-working",
    "genesis-verifying",
    "genesis-autonomous",
    "genesis-deferred",
    "genesis-blocked",
    "genesis-solver-exhausted",
    "genesis-waiting-capability",
    "genesis-needs-human",
    "agentic-lab",
    "genesis-agentic-escalated",
    "genesis-qwen3-agentic",
    "genesis-deepseek-agentic",
    "genesis-recovery-solver",
)
RECONCILE_MARKER = "<!-- genesis-issue-lifecycle-reconcile -->"


def request(repository: str, token: str, method: str, path: str, payload: dict | None = None):
    url = f"https://api.github.com/repos/{repository}{path}"
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "genesis-issue-lifecycle-manager",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            raw = response.read()
            return json.loads(raw.decode("utf-8")) if raw else None
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"GitHub API {method} {path} failed: HTTP {exc.code}: {body[:500]}") from exc


def all_issues(repository: str, token: str) -> list[dict]:
    rows: list[dict] = []
    page = 1
    while True:
        batch = request(repository, token, "GET", f"/issues?state=all&per_page=100&page={page}&sort=updated&direction=desc") or []
        issues = [row for row in batch if isinstance(row, dict) and "pull_request" not in row]
        rows.extend(issues)
        if len(batch) < 100:
            break
        page += 1
        if page > 20:
            break
    return rows


def issue_comments(repository: str, token: str, number: int) -> list[dict]:
    rows: list[dict] = []
    page = 1
    while True:
        batch = request(repository, token, "GET", f"/issues/{number}/comments?per_page=100&page={page}") or []
        rows.extend(row for row in batch if isinstance(row, dict))
        if len(batch) < 100:
            break
        page += 1
    return rows


def ensure_label(repository: str, token: str, name: str, color: str, description: str) -> None:
    try:
        request(repository, token, "POST", "/labels", {"name": name, "color": color, "description": description})
    except RuntimeError as exc:
        if "HTTP 422" not in str(exc):
            raise


def remove_label(repository: str, token: str, number: int, label: str) -> None:
    encoded = urllib.parse.quote(label, safe="")
    try:
        request(repository, token, "DELETE", f"/issues/{number}/labels/{encoded}")
    except RuntimeError as exc:
        if "HTTP 404" not in str(exc):
            raise


def post_comment(repository: str, token: str, number: int, body: str) -> None:
    request(repository, token, "POST", f"/issues/{number}/comments", {"body": body})


def close_issue(repository: str, token: str, number: int, *, reason: str, reference: int | None) -> None:
    request(repository, token, "PATCH", f"/issues/{number}", {"state": "closed", "state_reason": "not_planned"})
    request(repository, token, "POST", f"/issues/{number}/labels", {"labels": ["genesis-superseded"]})
    for label in ACTIVE_LABELS:
        remove_label(repository, token, number, label)
    reference_text = f" Reference authoritative verified Issue: #{reference}." if reference else ""
    post_comment(
        repository,
        token,
        number,
        (
            f"{RECONCILE_MARKER}\n"
            f"Genesis Issue Lifecycle Manager closed this Issue because `{reason}`.{reference_text} "
            "Current repository authority/dependency state overrides stale retry history. "
            "No implementation acceptance criterion was waived."
        ),
    )


def reopen_issue(repository: str, token: str, number: int) -> None:
    request(repository, token, "PATCH", f"/issues/{number}", {"state": "open"})
    request(repository, token, "POST", f"/issues/{number}/labels", {"labels": ["genesis-autonomous"]})
    post_comment(
        repository,
        token,
        number,
        (
            f"{RECONCILE_MARKER}\n"
            "Genesis Issue Lifecycle Manager reopened this Issue because it is still an authoritative, unverified root task. "
            "The decision is based on current repository authority state rather than stale solver labels."
        ),
    )


def reconcile(repository: str, token: str, max_changes: int = 50) -> dict:
    ensure_label(
        repository,
        token,
        "genesis-superseded",
        "6e7781",
        "Closed because current repository authority shows this work is duplicate, superseded, or orphaned",
    )
    issues = all_issues(repository, token)
    by_number = {int(row.get("number") or 0): row for row in issues if int(row.get("number") or 0) > 0}
    changes: list[dict] = []

    for number in sorted(by_number):
        if len(changes) >= max_changes:
            break
        issue = by_number[number]
        comments: list[dict] = []
        if "<!-- genesis-capability-work:" in str(issue.get("body") or ""):
            comments = issue_comments(repository, token, number)
        decision = lifecycle_decision(issue, by_number, comments=comments)
        if decision.action in {"close_superseded", "close_duplicate"}:
            close_issue(
                repository,
                token,
                number,
                reason=decision.reason,
                reference=decision.reference_issue,
            )
            changes.append({
                "issue": number,
                "family_id": family_id(issue),
                "action": decision.action,
                "reason": decision.reason,
                "reference_issue": decision.reference_issue,
            })
            issue["state"] = "closed"
            issue.setdefault("labels", []).append({"name": "genesis-superseded"})

    for number in sorted(by_number):
        if len(changes) >= max_changes:
            break
        issue = by_number[number]
        if str(issue.get("state") or "").lower() != "closed":
            continue
        decision = lifecycle_decision(issue, by_number)
        if decision.action == "reopen":
            reopen_issue(repository, token, number)
            changes.append({
                "issue": number,
                "family_id": family_id(issue),
                "action": "reopen",
                "reason": decision.reason,
            })
            issue["state"] = "open"

    return {"status": "ok", "changes": changes, "change_count": len(changes)}


def main() -> int:
    repository = os.environ.get("GITHUB_REPOSITORY", "").strip()
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if not repository or not token:
        raise SystemExit("GITHUB_REPOSITORY and GITHUB_TOKEN are required")
    print(json.dumps(reconcile(repository, token), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
