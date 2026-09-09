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
from requeue_exhausted_issues import (
    _open_issues,
    create_successor_handoff,
    engine_generation,
    is_successor_issue,
)

RECOVERY_LABEL = "genesis-recovery-solver"
RECOVERY_TERMINAL_LABEL = "genesis-recovery-terminal"
RECOVERY_MARKER = "<!-- genesis-recovery-solver-cycle:"
RECOVERY_TERMINAL_MARKER = "<!-- genesis-recovery-terminal -->"
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
    return sum(
        1
        for row in comments
        if str(row.get("body") or "").startswith(RECOVERY_MARKER)
    )


def ensure_label(repository: str, token: str, name: str = RECOVERY_LABEL, color: str = "1d76db", description: str = "Dedicated second solver lane for exhausted or blocked Genesis Issues") -> None:
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


def _terminalize_successor(repository: str, token: str, issue: dict, comments: list[dict]) -> dict:
    number = int(issue.get("number") or 0)
    ensure_label(
        repository,
        token,
        RECOVERY_TERMINAL_LABEL,
        "6e7781",
        "Closed after bounded independent recovery exhausted without verified promotion",
    )
    request(
        repository,
        token,
        "POST",
        f"/issues/{number}/labels",
        {"labels": [RECOVERY_TERMINAL_LABEL, "genesis-solver-exhausted", "genesis-deferred"]},
    )
    for label in (
        "genesis-autonomous",
        "genesis-repair-in-progress",
        "genesis-validating",
        "genesis-working",
        "genesis-verifying",
        RECOVERY_LABEL,
    ):
        _remove_label(repository, token, number, label)

    if not any(RECOVERY_TERMINAL_MARKER in str(row.get("body") or "") for row in comments):
        request(
            repository,
            token,
            "POST",
            f"/issues/{number}/comments",
            {
                "body": (
                    f"{RECOVERY_TERMINAL_MARKER}\n"
                    f"Genesis exhausted {MAX_RECOVERY_CYCLES} independent Recovery Solver cycles without a verified promotion. "
                    "This Issue is already a repair successor, so Genesis will not create an unbounded successor chain. "
                    "It is closed as not planned with its evidence preserved. A materially new future issue may be created only from new evidence or a changed repair capability, not as an automatic duplicate retry."
                )
            },
        )
    request(repository, token, "PATCH", f"/issues/{number}", {"state": "closed", "state_reason": "not_planned"})
    return {"status": "closed_terminal_successor", "issue_number": number}


def finalize_exhausted_issue(repository: str, token: str, issue: dict, comments: list[dict]) -> dict:
    body = str(issue.get("body") or "")
    number = int(issue.get("number") or 0)

    if CAPABILITY_WORK_PREFIX in body:
        return {"status": "capability_dependency_exempt", "issue_number": number}

    if is_successor_issue(issue):
        return _terminalize_successor(repository, token, issue, comments)

    handoff = create_successor_handoff(
        repository,
        token,
        issue,
        _open_issues(repository, token),
        engine_generation(),
        comments,
    )
    return {
        "status": "successor_created_and_parent_closed",
        "issue_number": number,
        "successor": int(handoff.get("successor") or 0),
        "created": bool(handoff.get("created")),
    }


def reserve_and_dispatch(repository: str, token: str) -> dict:
    ensure_label(repository, token)
    for issue in open_agentic_issues(repository, token):
        number = int(issue.get("number") or 0)
        body = str(issue.get("body") or "")
        issue_labels = labels(issue)

        # Capability work has one authoritative lane: Agentic Lab capability-first.
        # Recovery Solver must never compete with it.
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

        # A finished/failed shared worker may leave the ownership marker behind.
        # It is advisory only when no active reservation exists, so clear it before reuse.
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
        strategy = RECOVERY_STRATEGIES[cycles % len(RECOVERY_STRATEGIES)]

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
