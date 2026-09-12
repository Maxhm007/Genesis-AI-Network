from __future__ import annotations

import json
import os

from agentic_lab_recovery_dispatch import (
    ACTIVE_LABELS,
    AGENTIC_LABEL,
    CAPABILITY_WORK_PREFIX,
    EXHAUSTED_LABEL,
    labels,
    open_agentic_issues,
    request,
    safe_lane,
    explicit_target,
)

RECOVERY_LABEL = "genesis-recovery-solver"
RECOVERY_ESCALATED_LABEL = "genesis-agentic-escalated"
RECOVERY_MARKER = "<!-- genesis-recovery-solver-cycle:"
RECOVERY_ESCALATED_MARKER = "<!-- genesis-recovery-same-issue-escalation -->"
# Every bounded recovery generation must start by checking current main. This
# prevents Genesis from blindly repairing stale Issues whose objective is already
# satisfied and makes the remaining strategies operate on fresh evidence.
RECOVERY_STRATEGIES = (
    "evidence_first",
    "diagnostic_reframe",
    "alternative_implementation",
    "dependency_diagnosis",
)
# Every declared recovery strategy must be reachable before same-Issue escalation.
# Keep the cycle budget derived from the strategy set so adding a strategy cannot
# silently make the final recovery method unreachable again.
MAX_RECOVERY_CYCLES = len(RECOVERY_STRATEGIES)


def issue_comments(repository: str, token: str, number: int) -> list[dict]:
    comments: list[dict] = []
    page = 1
    while True:
        rows = request(
            repository,
            token,
            "GET",
            f"/issues/{number}/comments?per_page=100&page={page}",
        ) or []
        page_rows = [row for row in rows if isinstance(row, dict)]
        comments.extend(page_rows)
        if len(rows) < 100:
            break
        page += 1
    return comments


def recovery_cycle_count(comments: list[dict]) -> int:
    return sum(
        1
        for row in comments
        if str(row.get("body") or "").startswith(RECOVERY_MARKER)
    )


def ensure_label(
    repository: str,
    token: str,
    name: str = RECOVERY_LABEL,
    color: str = "1d76db",
    description: str = "Dedicated second solver lane for exhausted or blocked Genesis Issues",
) -> None:
    try:
        request(
            repository,
            token,
            "POST",
            "/labels",
            {"name": name, "color": color, "description": description},
        )
    except RuntimeError as exc:
        if "HTTP 422" not in str(exc):
            raise


def _remove_label(repository: str, token: str, number: int, label: str) -> None:
    try:
        request(repository, token, "DELETE", f"/issues/{number}/labels/{label}")
    except RuntimeError:
        pass


def finalize_exhausted_issue(repository: str, token: str, issue: dict, comments: list[dict]) -> dict:
    """Escalate recovery exhaustion without creating or closing a successor Issue.

    The same GitHub Issue remains authoritative. Recovery Solver stops claiming it,
    while Agentic Lab keeps ownership and may choose a materially different strategy
    or capability-growth path. This prevents duplicate repair-follow-up chains.
    """
    body = str(issue.get("body") or "")
    number = int(issue.get("number") or 0)

    if CAPABILITY_WORK_PREFIX in body:
        return {"status": "capability_dependency_exempt", "issue_number": number}

    fresh = request(repository, token, "GET", f"/issues/{number}")
    fresh_issue = fresh if isinstance(fresh, dict) else issue
    fresh_labels = labels(fresh_issue)
    if str(fresh_issue.get("state") or "open") == "closed":
        return {"status": "closed_issue_ignored", "issue_number": number}
    if RECOVERY_ESCALATED_LABEL in fresh_labels:
        return {"status": "already_escalated_same_issue", "issue_number": number}

    ensure_label(
        repository,
        token,
        RECOVERY_ESCALATED_LABEL,
        "8250df",
        "Recovery Solver exhausted; same authoritative Issue remains with Agentic Lab",
    )
    request(
        repository,
        token,
        "POST",
        f"/issues/{number}/labels",
        {
            "labels": [
                RECOVERY_ESCALATED_LABEL,
                AGENTIC_LABEL,
                EXHAUSTED_LABEL,
                "genesis-blocked",
            ]
        },
    )

    for label in (
        RECOVERY_LABEL,
        "genesis-repair-in-progress",
        "genesis-validating",
        "genesis-working",
        "genesis-verifying",
    ):
        _remove_label(repository, token, number, label)

    if not any(RECOVERY_ESCALATED_MARKER in str(row.get("body") or "") for row in comments):
        request(
            repository,
            token,
            "POST",
            f"/issues/{number}/comments",
            {
                "body": (
                    f"{RECOVERY_ESCALATED_MARKER}\n"
                    f"Genesis exhausted {MAX_RECOVERY_CYCLES} bounded Recovery Solver cycles without verified promotion. "
                    "This same Issue remains open and authoritative under Agentic Lab. No repair follow-up/successor Issue is created. "
                    "Agentic Lab must continue only with a materially different strategy or a reusable capability-growth path, while preserving all existing security, validation, protected-file, signing, secret, promotion, and owner-control boundaries."
                )
            },
        )

    return {"status": "same_issue_agentic_lab_escalation", "issue_number": number}


def reserve_and_dispatch(repository: str, token: str) -> dict:
    ensure_label(repository, token)
    for issue in open_agentic_issues(repository, token):
        number = int(issue.get("number") or 0)
        body = str(issue.get("body") or "")
        issue_labels = labels(issue)

        if RECOVERY_ESCALATED_LABEL in issue_labels:
            continue

        if CAPABILITY_WORK_PREFIX in body:
            if RECOVERY_LABEL in issue_labels and not (issue_labels & ACTIVE_LABELS):
                _remove_label(repository, token, number, RECOVERY_LABEL)
            continue

        if EXHAUSTED_LABEL not in issue_labels:
            continue
        if issue_labels & ACTIVE_LABELS:
            continue
        if "genesis-waiting-capability" in issue_labels:
            continue

        if RECOVERY_LABEL in issue_labels:
            _remove_label(repository, token, number, RECOVERY_LABEL)

        target = explicit_target(body)
        lane = safe_lane(target)
        if not lane:
            continue

        comments = issue_comments(repository, token, number)
        cycles = recovery_cycle_count(comments)
        if cycles >= MAX_RECOVERY_CYCLES:
            outcome = finalize_exhausted_issue(repository, token, issue, comments)
            if outcome.get("status") == "capability_dependency_exempt":
                continue
            return outcome

        cycle = cycles + 1
        strategy = RECOVERY_STRATEGIES[cycles]

        # The downstream repair engine requires genesis-autonomous. Recovery used
        # to reserve only the Agentic/repair labels, which could make an otherwise
        # eligible worker fail with authorization_label_missing.
        request(
            repository,
            token,
            "POST",
            f"/issues/{number}/labels",
            {
                "labels": [
                    RECOVERY_LABEL,
                    "genesis-repair-in-progress",
                    "genesis-autonomous",
                    AGENTIC_LABEL,
                ]
            },
        )
        fresh = request(repository, token, "GET", f"/issues/{number}")
        fresh_labels = labels(fresh if isinstance(fresh, dict) else {})
        if (
            "genesis-repair-in-progress" not in fresh_labels
            or RECOVERY_LABEL not in fresh_labels
            or "genesis-autonomous" not in fresh_labels
        ):
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
                    f"It will use recovery strategy (`{strategy}`) while preserving the same Issue authority, validation, security, and exact-promotion gates. "
                    "Cycle 1 is always evidence-first so current main is checked before any new repair is attempted."
                )
            },
        )
        try:
            request(
                repository,
                token,
                "POST",
                "/actions/workflows/genesis-agentic-strategy-worker.yml/dispatches",
                {"ref": "main", "inputs": {"issue_number": str(number), "strategy": strategy}},
            )
        except Exception:
            _remove_label(repository, token, number, "genesis-repair-in-progress")
            _remove_label(repository, token, number, RECOVERY_LABEL)
            raise
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
