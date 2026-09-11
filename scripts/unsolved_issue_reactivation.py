from __future__ import annotations

import argparse
import json
import os
import urllib.error
import urllib.parse
import urllib.request


AGENTIC_LABEL = "agentic-lab"
EXHAUSTED_LABEL = "genesis-solver-exhausted"
DEFERRED_LABEL = "genesis-deferred"
VERIFIED_LABEL = "genesis-verified"
SUPERSEDED_LABEL = "genesis-superseded"
TERMINAL_LABEL = "genesis-terminal"
TERMINAL_MARKER = "<!-- genesis-agentic-terminal-reconcile -->"
MARKER = "<!-- genesis-unsolved-strategy-reactivation -->"
ACTIVE_LABELS = (
    "genesis-repair-in-progress",
    "genesis-validating",
    "genesis-claimed",
    "genesis-working",
    "genesis-verifying",
    "genesis-autonomous",
)
FAILURE_PHRASES = (
    "Genesis bounded repair did not promote a verified change",
    "Genesis specialist repair exhausted its bounded attempt set",
    "Genesis Sequential Issue Controller — bounded attempt exhausted",
    "terminally deferred under the current repair-engine generation",
)


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
            "User-Agent": "Genesis-AI-Network/unsolved-issue-reactivation",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            raw = response.read().decode("utf-8")
        return json.loads(raw) if raw.strip() else {}
    except urllib.error.HTTPError as exc:
        if method == "DELETE" and exc.code == 404:
            return {}
        detail = exc.read().decode("utf-8", errors="replace")[:1000]
        raise RuntimeError(f"GitHub HTTP {exc.code} for {method} {path}: {detail}") from exc


def labels(issue: dict) -> set[str]:
    result: set[str] = set()
    for row in issue.get("labels") or []:
        if isinstance(row, dict):
            name = str(row.get("name") or "").strip()
        else:
            name = str(row or "").strip()
        if name:
            result.add(name)
    return result


def remove_label(repository: str, token: str, number: int, label: str) -> None:
    request(repository, token, "DELETE", f"/issues/{number}/labels/{urllib.parse.quote(label, safe='')}")


def ensure_agentic_label(repository: str, token: str) -> None:
    try:
        request(
            repository,
            token,
            "POST",
            "/labels",
            {
                "name": AGENTIC_LABEL,
                "color": "8250df",
                "description": "Normal bounded method failed; Agentic Lab owns strategy rotation for this open Issue",
            },
        )
    except RuntimeError as exc:
        if "HTTP 422" not in str(exc):
            raise


def has_solver_failure_evidence(comments: list[dict]) -> bool:
    for row in reversed(comments):
        body = str(row.get("body") or "")
        if any(phrase in body for phrase in FAILURE_PHRASES):
            return True
    return False


def has_terminal_reconcile_evidence(comments: list[dict]) -> bool:
    return any(TERMINAL_MARKER in str(row.get("body") or "") for row in comments)


def reactivate(repository: str, token: str, issue_number: int) -> dict:
    number = int(issue_number)
    issue = request(repository, token, "GET", f"/issues/{number}")
    if not isinstance(issue, dict):
        raise RuntimeError("GitHub did not return a valid Issue")

    state = str(issue.get("state") or "").lower()
    issue_labels = labels(issue)
    if state != "closed":
        return {"status": "ignored", "issue_number": number, "reason": "issue_not_closed"}
    if VERIFIED_LABEL in issue_labels:
        return {"status": "ignored", "issue_number": number, "reason": "verified_closure"}
    if SUPERSEDED_LABEL in issue_labels:
        return {"status": "ignored", "issue_number": number, "reason": "superseded_closure"}
    if TERMINAL_LABEL in issue_labels:
        return {"status": "ignored", "issue_number": number, "reason": "terminal_closure"}

    comments = request(repository, token, "GET", f"/issues/{number}/comments?per_page=100") or []
    comments = [row for row in comments if isinstance(row, dict)]
    if has_terminal_reconcile_evidence(comments):
        return {"status": "ignored", "issue_number": number, "reason": "terminal_reconcile_evidence"}

    if not ({EXHAUSTED_LABEL, DEFERRED_LABEL} & issue_labels):
        return {"status": "ignored", "issue_number": number, "reason": "not_solver_exhaustion"}
    if not has_solver_failure_evidence(comments):
        return {"status": "ignored", "issue_number": number, "reason": "no_solver_failure_evidence"}

    ensure_agentic_label(repository, token)
    request(
        repository,
        token,
        "POST",
        f"/issues/{number}/labels",
        {"labels": [AGENTIC_LABEL, EXHAUSTED_LABEL]},
    )
    for label in (*ACTIVE_LABELS, DEFERRED_LABEL):
        remove_label(repository, token, number, label)

    reopened = request(repository, token, "PATCH", f"/issues/{number}", {"state": "open"})
    if not isinstance(reopened, dict) or str(reopened.get("state") or "").lower() != "open":
        raise RuntimeError("Genesis-unsolved Issue could not be reopened for strategy rotation")

    if not any(MARKER in str(row.get("body") or "") for row in comments):
        request(
            repository,
            token,
            "POST",
            f"/issues/{number}/comments",
            {
                "body": (
                    f"{MARKER}\n"
                    "Genesis did not verify a solution, so this Issue must remain open. The exhausted bounded method is recorded as evidence and control is transferred to Agentic Lab for a materially different strategy. "
                    "If the remaining blocker is a missing Genesis capability, Agentic Lab must create/reuse a linked capability Issue and pause this parent Issue instead of closing it."
                )
            },
        )

    try:
        request(
            repository,
            token,
            "POST",
            "/actions/workflows/genesis-agentic-lab-recovery.yml/dispatches",
            {"ref": "main"},
        )
    except Exception:
        pass

    return {"status": "reactivated", "issue_number": number, "next_owner": AGENTIC_LABEL}


def main() -> None:
    parser = argparse.ArgumentParser(description="Keep Genesis-unsolved Issues open and rotate recovery strategy")
    parser.add_argument("--issue-number", type=int, required=True)
    parser.add_argument("--repository", default=os.environ.get("GITHUB_REPOSITORY", ""))
    args = parser.parse_args()
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if not args.repository or not token:
        raise SystemExit("repository and GITHUB_TOKEN are required")
    print(json.dumps(reactivate(args.repository, token, args.issue_number), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
