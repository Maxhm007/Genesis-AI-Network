from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request


STRATEGY_PREFIX = "<!-- genesis-agentic-strategy:"
RESULT_PREFIX = "<!-- genesis-agentic-strategy-result:"
REACTIVATE_PREFIX = "<!-- genesis-agentic-reactivate -->"
RETRY_PREFIX = "<!-- genesis-agentic-retry-cycle -->"
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
            "User-Agent": "Genesis-AI-Network/agentic-retry-cycle",
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


def remove_label(repository: str, token: str, number: int, label: str) -> None:
    request(repository, token, "DELETE", f"/issues/{number}/labels/{urllib.parse.quote(label, safe='')}")


def _reactivate_waiting_issue(repository: str, token: str, issue: dict) -> bool:
    number = int(issue.get("number") or 0)
    issue_labels = labels(issue)
    if WAITING_LABEL not in issue_labels or VERIFIED_LABEL in issue_labels or number <= 1:
        return False

    for label in ACTIVE_LABELS | {WAITING_LABEL, "genesis-deferred", "genesis-blocked"}:
        remove_label(repository, token, number, label)
    request(repository, token, "POST", f"/issues/{number}/labels", {"labels": [AGENTIC_LABEL, AUTONOMOUS_LABEL, "genesis-solver-exhausted"]})
    request(
        repository,
        token,
        "POST",
        f"/issues/{number}/comments",
        {
            "body": (
                f"{RETRY_PREFIX}\n"
                "Genesis restored this unsolved Issue to Agentic Lab. Exhausting a strategy set is not completion. "
                "The same Issue stays OPEN and authoritative; Agentic Lab will continue with another materially different or least-recently-used strategy until verification succeeds."
            )
        },
    )
    return True


def park_issue(repository: str, token: str, issue: dict) -> bool:
    """Keep exhausted Agentic work open and eligible instead of parking it.

    Historical callers still use this function name. It now enforces the global
    lifecycle rule: failed attempts change strategy, never Issue state.
    """
    number = int(issue.get("number") or 0)
    issue_labels = labels(issue)
    if number <= 1 or VERIFIED_LABEL in issue_labels:
        return False

    if WAITING_LABEL in issue_labels:
        return _reactivate_waiting_issue(repository, token, issue)

    if not ({AGENTIC_LABEL, AUTONOMOUS_LABEL} & issue_labels):
        return False
    if issue_labels & ACTIVE_LABELS:
        return False

    rows = comments(repository, token, number)
    attempted = attempted_strategies(rows)
    if attempted != STRATEGIES or not has_failed_results(rows):
        return False

    # All known strategies have been tried, but the Issue is still unsolved.
    # Keep it in Agentic Lab and allow the FIFO dispatcher to rotate strategies
    # again using the accumulated comments as repair memory.
    request(repository, token, "POST", f"/issues/{number}/labels", {"labels": [AGENTIC_LABEL, AUTONOMOUS_LABEL, "genesis-solver-exhausted"]})
    for label in {WAITING_LABEL, "genesis-deferred", "genesis-blocked"}:
        remove_label(repository, token, number, label)

    active_rows = active_attempt_rows(rows)
    if not any(str(row.get("body") or "").startswith(RETRY_PREFIX) for row in active_rows):
        request(
            repository,
            token,
            "POST",
            f"/issues/{number}/comments",
            {
                "body": (
                    f"{RETRY_PREFIX}\n"
                    "Agentic Lab completed one full strategy rotation without a verified solution. "
                    "The Issue remains OPEN and authoritative. The next pass will retry with a different/least-recently-used strategy, "
                    "using the existing failure comments as repair memory. Strategy exhaustion does not close or park the Issue."
                )
            },
        )
    print(json.dumps({"status": "agentic_retry_cycle", "issue_number": number, "attempted_strategies": sorted(attempted)}, sort_keys=True))
    return True


def main() -> int:
    repository = os.environ.get("GITHUB_REPOSITORY", "").strip()
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if not repository or not token:
        raise RuntimeError("GITHUB_REPOSITORY and GITHUB_TOKEN are required")

    recycled: list[int] = []
    for page in range(1, 101):
        batch = request(repository, token, "GET", f"/issues?state=open&sort=created&direction=asc&per_page=100&page={page}") or []
        if not isinstance(batch, list):
            break
        for issue in batch:
            if isinstance(issue, dict) and not issue.get("pull_request") and park_issue(repository, token, issue):
                recycled.append(int(issue.get("number") or 0))
        if len(batch) < 100:
            break

    print(json.dumps({"agentic_retry_issues": recycled, "count": len(recycled)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
