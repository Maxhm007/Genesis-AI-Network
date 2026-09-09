from __future__ import annotations

import json
import os

from agentic_lab_recovery_dispatch import (
    ACTIVE_LABELS,
    AGENTIC_LABEL,
    EXHAUSTED_LABEL,
    labels,
    open_agentic_issues,
    request,
    safe_lane,
    explicit_target,
)

RECOVERY_LABEL = "genesis-recovery-solver"
RECOVERY_MARKER = "<!-- genesis-recovery-solver-cycle:"
RECOVERY_STRATEGIES = (
    "diagnostic_reframe",
    "dependency_diagnosis",
    "alternative_implementation",
    "evidence_first",
)
MAX_RECOVERY_CYCLES = 3


def issue_comments(repository: str, token: str, number: int) -> list[dict]:
    rows = request(repository, token, "GET", f"/issues/{number}/comments?per_page=100") or []
    return [row for row in rows if isinstance(row, dict)]


def recovery_cycle_count(comments: list[dict]) -> int:
    count = 0
    for row in comments:
        body = str(row.get("body") or "")
        if body.startswith(RECOVERY_MARKER):
            count += 1
    return count


def recovery_strategies_used(comments: list[dict], cycle: int) -> set[str]:
    marker = f"{RECOVERY_MARKER}{cycle} -->"
    start = -1
    for index, row in enumerate(comments):
        if str(row.get("body") or "").startswith(marker):
            start = index
    used: set[str] = set()
    if start < 0:
        return used
    for row in comments[start + 1 :]:
        body = str(row.get("body") or "")
        if not body.startswith("<!-- genesis-agentic-strategy:"):
            continue
        strategy = body.split("<!-- genesis-agentic-strategy:", 1)[1].split("-->", 1)[0].strip()
        if strategy:
            used.add(strategy)
    return used


def ensure_label(repository: str, token: str) -> None:
    try:
        request(
            repository,
            token,
            "POST",
            "/labels",
            {
                "name": RECOVERY_LABEL,
                "color": "1d76db",
                "description": "Dedicated second solver lane for exhausted or blocked Genesis Issues",
            },
        )
    except RuntimeError as exc:
        if "HTTP 422" not in str(exc):
            raise


def reserve_and_dispatch(repository: str, token: str) -> dict:
    ensure_label(repository, token)
    for issue in open_agentic_issues(repository, token):
        number = int(issue.get("number") or 0)
        issue_labels = labels(issue)
        if EXHAUSTED_LABEL not in issue_labels:
            continue
        if issue_labels & ACTIVE_LABELS:
            continue
        if "genesis-waiting-capability" in issue_labels:
            continue

        target = explicit_target(str(issue.get("body") or ""))
        lane = safe_lane(target)
        if not lane:
            continue

        comments = issue_comments(repository, token, number)
        cycles = recovery_cycle_count(comments)
        if cycles >= MAX_RECOVERY_CYCLES:
            continue

        cycle = cycles + 1
        used = recovery_strategies_used(comments, cycle)
        strategy = next((item for item in RECOVERY_STRATEGIES if item not in used), RECOVERY_STRATEGIES[0])

        # Claim first; the shared worker also has per-Issue concurrency protection.
        request(
            repository,
            token,
            "POST",
            f"/issues/{number}/labels",
            {"labels": [RECOVERY_LABEL, "genesis-repair-in-progress", AGENTIC_LABEL]},
        )
        fresh = request(repository, token, "GET", f"/issues/{number}")
        fresh_labels = labels(fresh if isinstance(fresh, dict) else {})
        if "genesis-repair-in-progress" not in fresh_labels or RECOVERY_LABEL not in fresh_labels:
            continue

        marker = f"{RECOVERY_MARKER}{cycle} -->"
        request(
            repository,
            token,
            "POST",
            f"/issues/{number}/comments",
            {
                "body": (
                    f"{marker}\n"
                    f"Dedicated Recovery Solver claimed exhausted Issue #{number} for bounded recovery cycle {cycle}/{MAX_RECOVERY_CYCLES}. "
                    f"It will use a different recovery-first strategy (`{strategy}`) while preserving the same Issue authority, validation, security, and exact-promotion gates."
                )
            },
        )
        request(
            repository,
            token,
            "POST",
            "/actions/workflows/genesis-agentic-strategy-worker.yml/dispatches",
            {"ref": "main", "inputs": {"issue_number": str(number), "strategy": strategy}},
        )
        return {
            "status": "dispatched",
            "issue_number": number,
            "strategy": strategy,
            "cycle": cycle,
            "lane": lane,
        }
    return {"status": "idle", "reason": "no eligible exhausted Agentic Lab issue"}


def main() -> int:
    repository = os.environ.get("GITHUB_REPOSITORY", "").strip()
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if not repository or not token:
        raise SystemExit("GITHUB_REPOSITORY and GITHUB_TOKEN are required")
    print(json.dumps(reserve_and_dispatch(repository, token), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
