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
QWEN3_ATTEMPT_PREFIX = "<!-- genesis-qwen3-agentic-attempt -->"
QWEN3_RESULT_PREFIX = "<!-- genesis-agentic-strategy-result:qwen3_fallback -->"
WAITING_LABEL = "genesis-waiting-user"
AGENTIC_LABEL = "agentic-lab"
AUTONOMOUS_LABEL = "genesis-autonomous"
VERIFIED_LABEL = "genesis-verified"
QWEN3_LABEL = "genesis-qwen3-agentic"
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
            "User-Agent": "Genesis-AI-Network/agentic-qwen3-fallback",
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
    return {str(row.get("name") if isinstance(row, dict) else row) for row in issue.get("labels") or []}


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


def current_agentic_cycle_rows(rows: list[dict]) -> list[dict]:
    active = active_attempt_rows(rows)
    last_qwen3_result = -1
    for index, row in enumerate(active):
        if str(row.get("body") or "").startswith(QWEN3_RESULT_PREFIX):
            last_qwen3_result = index
    return active[last_qwen3_result + 1 :]


def attempted_strategies(rows: list[dict]) -> set[str]:
    attempted: set[str] = set()
    for row in current_agentic_cycle_rows(rows):
        body = str(row.get("body") or "")
        if body.startswith(STRATEGY_PREFIX):
            strategy = body[len(STRATEGY_PREFIX):].split("-->", 1)[0].strip()
            if strategy in STRATEGIES:
                attempted.add(strategy)
    return attempted


def has_failed_results(rows: list[dict]) -> bool:
    return any(str(row.get("body") or "").startswith(RESULT_PREFIX) for row in current_agentic_cycle_rows(rows))


def remove_label(repository: str, token: str, number: int, label: str) -> None:
    request(repository, token, "DELETE", f"/issues/{number}/labels/{urllib.parse.quote(label, safe='')}")


def ensure_qwen3_label(repository: str, token: str) -> None:
    try:
        request(repository, token, "POST", "/labels", {
            "name": QWEN3_LABEL,
            "color": "5319e7",
            "description": "Last-resort Qwen3 Agentic recovery after the existing Agentic strategy set fails",
        })
    except urllib.error.HTTPError as exc:
        if exc.code != 422:
            raise


def _reactivate_waiting_issue(repository: str, token: str, issue: dict) -> bool:
    number = int(issue.get("number") or 0)
    issue_labels = labels(issue)
    if WAITING_LABEL not in issue_labels or VERIFIED_LABEL in issue_labels or number <= 1:
        return False
    for label in ACTIVE_LABELS | {WAITING_LABEL, "genesis-deferred", "genesis-blocked", QWEN3_LABEL}:
        remove_label(repository, token, number, label)
    request(repository, token, "POST", f"/issues/{number}/labels", {"labels": [AGENTIC_LABEL, AUTONOMOUS_LABEL, "genesis-solver-exhausted"]})
    request(repository, token, "POST", f"/issues/{number}/comments", {"body": (
        f"{RETRY_PREFIX}\nGenesis restored this unsolved Issue to Agentic Lab. Exhausting a strategy set is not completion. "
        "The same Issue stays OPEN and authoritative and will continue through Agentic recovery, including the Qwen3 fallback after a full failed strategy rotation."
    )})
    return True


def _dispatch_qwen3(repository: str, token: str, number: int) -> bool:
    request(repository, token, "POST", f"/issues/{number}/labels", {"labels": [
        AGENTIC_LABEL, AUTONOMOUS_LABEL, "genesis-solver-exhausted", QWEN3_LABEL, "genesis-repair-in-progress"
    ]})
    request(repository, token, "POST", f"/issues/{number}/comments", {"body": (
        f"{QWEN3_ATTEMPT_PREFIX}\nThe existing Agentic Lab strategy set completed without a verified solution. "
        "Genesis is escalating the SAME open Issue to the Qwen3 Agentic fallback through the standard Agentic Strategy Worker. "
        "Qwen3 must still pass exact-scope, validation, promotion, and verify-before-close gates."
    )})
    try:
        request(repository, token, "POST", "/actions/workflows/genesis-agentic-strategy-worker.yml/dispatches", {
            "ref": "main",
            "inputs": {"issue_number": str(number), "strategy": "qwen3_fallback"},
        })
    except Exception:
        remove_label(repository, token, number, "genesis-repair-in-progress")
        remove_label(repository, token, number, QWEN3_LABEL)
        request(repository, token, "POST", f"/issues/{number}/comments", {"body": (
            "<!-- genesis-qwen3-agentic-dispatch-failed -->\nQwen3 Agentic dispatch failed before a repair attempt started. "
            "The Issue remains OPEN and authoritative; Agentic Lab may retry the same recovery cycle."
        )})
        return False
    return True


def park_issue(repository: str, token: str, issue: dict) -> bool:
    """Escalate a fully exhausted Agentic strategy cycle to Qwen3 without closing the Issue."""
    number = int(issue.get("number") or 0)
    issue_labels = labels(issue)
    if number <= 1 or VERIFIED_LABEL in issue_labels:
        return False
    if WAITING_LABEL in issue_labels:
        return _reactivate_waiting_issue(repository, token, issue)
    if not ({AGENTIC_LABEL, AUTONOMOUS_LABEL} & issue_labels):
        return False
    if issue_labels & ACTIVE_LABELS or QWEN3_LABEL in issue_labels:
        return False

    rows = comments(repository, token, number)
    attempted = attempted_strategies(rows)
    if attempted != STRATEGIES or not has_failed_results(rows):
        return False

    for label in {WAITING_LABEL, "genesis-deferred", "genesis-blocked"}:
        remove_label(repository, token, number, label)
    dispatched = _dispatch_qwen3(repository, token, number)
    print(json.dumps({
        "status": "qwen3_agentic_dispatched" if dispatched else "qwen3_agentic_dispatch_failed",
        "issue_number": number,
        "attempted_strategies": sorted(attempted),
    }, sort_keys=True))
    return dispatched


def main() -> int:
    repository = os.environ.get("GITHUB_REPOSITORY", "").strip()
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if not repository or not token:
        raise RuntimeError("GITHUB_REPOSITORY and GITHUB_TOKEN are required")
    ensure_qwen3_label(repository, token)
    escalated: list[int] = []
    for page in range(1, 101):
        batch = request(repository, token, "GET", f"/issues?state=open&sort=created&direction=asc&per_page=100&page={page}") or []
        if not isinstance(batch, list):
            break
        for issue in batch:
            if isinstance(issue, dict) and not issue.get("pull_request") and park_issue(repository, token, issue):
                escalated.append(int(issue.get("number") or 0))
        if len(batch) < 100:
            break
    print(json.dumps({"qwen3_agentic_issues": escalated, "count": len(escalated)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
