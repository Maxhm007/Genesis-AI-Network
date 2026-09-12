from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request


STRATEGY_PREFIX = "<!-- genesis-agentic-strategy:"
RESULT_PREFIX = "<!-- genesis-agentic-strategy-result:"
REACTIVATE_PREFIX = "<!-- genesis-agentic-reactivate -->"
WAITING_LABEL = "genesis-waiting-user"
AGENTIC_LABEL = "agentic-lab"
AUTONOMOUS_LABEL = "genesis-autonomous"
VERIFIED_LABEL = "genesis-verified"
ACTIVE_LABELS = {
    "genesis-repair-in-progress",
    "genesis-validating",
    "genesis-claimed",
    "genesis-working",
    "genesis-verifying",
}
STRATEGIES = {
    "evidence_first",
    "alternative_implementation",
    "diagnostic_reframe",
    "dependency_diagnosis",
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
            "User-Agent": "Genesis-AI-Network/exhausted-issue-parker",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            raw = response.read().decode("utf-8")
        return json.loads(raw) if raw.strip() else {}
    except urllib.error.HTTPError as exc:
        if method == "DELETE" and exc.code == 404:
            return {}
        raise


def labels(issue: dict) -> set[str]:
    return {
        str(row.get("name") if isinstance(row, dict) else row)
        for row in issue.get("labels") or []
    }


def comments(repository: str, token: str, number: int) -> list[dict]:
    rows: list[dict] = []
    for page in range(1, 101):
        batch = request(repository, token, "GET", f"/issues/{number}/comments?per_page=100&page={page}") or []
        if not isinstance(batch, list):
            break
        rows.extend(row for row in batch if isinstance(row, dict))
        if len(batch) < 100:
            break
    return rows


def active_attempt_rows(rows: list[dict]) -> list[dict]:
    """Return only comments in the current bounded attempt generation.

    A trusted maintainer/user may explicitly reactivate a parked issue after the
    repair engine itself has been improved. Old strategy history must remain as
    evidence, but it must not instantly exhaust the new bounded generation.
    """
    last_reactivate = -1
    for index, row in enumerate(rows):
        body = str(row.get("body") or "").strip()
        association = str(row.get("author_association") or "").upper()
        if body.startswith(REACTIVATE_PREFIX) and association in {"OWNER", "MEMBER", "COLLABORATOR"}:
            last_reactivate = index
    return rows[last_reactivate + 1 :]


def attempted_strategies(rows: list[dict]) -> set[str]:
    attempted: set[str] = set()
    for row in active_attempt_rows(rows):
        body = str(row.get("body") or "")
        if body.startswith(STRATEGY_PREFIX):
            strategy = body[len(STRATEGY_PREFIX):].split("-->", 1)[0].strip()
            if strategy in STRATEGIES:
                attempted.add(strategy)
    return attempted


def has_failed_results(rows: list[dict]) -> bool:
    return any(str(row.get("body") or "").startswith(RESULT_PREFIX) for row in active_attempt_rows(rows))


def ensure_label(repository: str, token: str) -> None:
    payload = {
        "name": WAITING_LABEL,
        "color": "fbca04",
        "description": "Open and unsolved; Genesis exhausted bounded attempts and moved to the next Issue",
    }
    try:
        request(repository, token, "POST", "/labels", payload)
    except urllib.error.HTTPError as exc:
        if exc.code != 422:
            raise


def remove_label(repository: str, token: str, number: int, label: str) -> None:
    request(repository, token, "DELETE", f"/issues/{number}/labels/{urllib.parse.quote(label, safe='')}")


def park_issue(repository: str, token: str, issue: dict) -> bool:
    number = int(issue.get("number") or 0)
    issue_labels = labels(issue)
    if number <= 1 or VERIFIED_LABEL in issue_labels or WAITING_LABEL in issue_labels:
        return False
    if not ({AGENTIC_LABEL, AUTONOMOUS_LABEL} & issue_labels):
        return False
    if issue_labels & ACTIVE_LABELS:
        return False

    rows = comments(repository, token, number)
    attempted = attempted_strategies(rows)
    if attempted != STRATEGIES or not has_failed_results(rows):
        return False

    request(repository, token, "POST", f"/issues/{number}/labels", {"labels": [WAITING_LABEL, "genesis-solver-exhausted"]})
    for label in ACTIVE_LABELS | {AGENTIC_LABEL, AUTONOMOUS_LABEL, "genesis-agentic-escalated", "genesis-blocked", "genesis-deferred"}:
        remove_label(repository, token, number, label)

    request(
        repository,
        token,
        "POST",
        f"/issues/{number}/comments",
        {
            "body": (
                "<!-- genesis-waiting-user -->\n"
                "Genesis completed the bounded Agentic attempt set without a verified solution. "
                "This Issue stays OPEN for maintainer review and no longer blocks FIFO. Genesis is moving to the next Issue."
            )
        },
    )
    print(json.dumps({"status": "parked", "issue_number": number, "attempted_strategies": sorted(attempted)}, sort_keys=True))
    return True


def main() -> int:
    repository = os.environ.get("GITHUB_REPOSITORY", "").strip()
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if not repository or not token:
        raise RuntimeError("GITHUB_REPOSITORY and GITHUB_TOKEN are required")

    ensure_label(repository, token)
    parked: list[int] = []
    for page in range(1, 101):
        batch = request(repository, token, "GET", f"/issues?state=open&sort=created&direction=asc&per_page=100&page={page}") or []
        if not isinstance(batch, list):
            break
        for issue in batch:
            if isinstance(issue, dict) and not issue.get("pull_request") and park_issue(repository, token, issue):
                parked.append(int(issue.get("number") or 0))
        if len(batch) < 100:
            break

    print(json.dumps({"parked_issues": parked, "count": len(parked)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
