from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Callable, Iterable

from .issue_fingerprint import canonical_issue_fingerprint


GithubRequester = Callable[[str, str, dict | None], object]
GENESIS_TASK_MARKER = "<!-- genesis-task-id:"
DUPLICATE_LABEL = "duplicate"


def _issue_number(issue: dict) -> int:
    try:
        return int(issue.get("number") or 0)
    except (TypeError, ValueError):
        return 0


def _created_sort_key(issue: dict) -> tuple[str, int]:
    created = str(issue.get("created_at") or "")
    # ISO-8601 strings from GitHub sort chronologically. Missing timestamps sort
    # after real timestamps and issue number provides a deterministic fallback.
    return (created or "9999-12-31T23:59:59Z", _issue_number(issue))


def _is_authoritative_open_task(issue: dict) -> bool:
    if not isinstance(issue, dict) or "pull_request" in issue:
        return False
    if str(issue.get("state") or "open").lower() != "open":
        return False
    body = str(issue.get("body") or "")
    if GENESIS_TASK_MARKER not in body:
        return False
    return bool(canonical_issue_fingerprint(body))


def build_reconciliation_plan(issues: Iterable[dict]) -> dict:
    """Return an exact-fingerprint duplicate plan without mutating GitHub.

    Only open issues carrying the authoritative Genesis task marker are eligible.
    Manual issues, reports, controls, escalations, action-failure channels and
    unparseable legacy records therefore stay outside the plan by construction.
    """

    groups: dict[str, list[dict]] = defaultdict(list)
    eligible = 0
    for issue in issues:
        if not _is_authoritative_open_task(issue):
            continue
        fingerprint = canonical_issue_fingerprint(str(issue.get("body") or ""))
        if not fingerprint:
            continue
        eligible += 1
        groups[fingerprint].append(issue)

    duplicate_groups: list[dict] = []
    duplicate_count = 0
    for fingerprint, rows in sorted(groups.items()):
        if len(rows) < 2:
            continue
        ordered = sorted(rows, key=_created_sort_key)
        primary = ordered[0]
        duplicates = ordered[1:]
        duplicate_numbers = [_issue_number(row) for row in duplicates if _issue_number(row)]
        if not duplicate_numbers or not _issue_number(primary):
            continue
        duplicate_count += len(duplicate_numbers)
        duplicate_groups.append(
            {
                "fingerprint": fingerprint,
                "primary_issue": _issue_number(primary),
                "duplicate_issues": duplicate_numbers,
                "reason": "exact_canonical_fingerprint_match",
            }
        )

    duplicate_groups.sort(key=lambda row: (row["primary_issue"], row["fingerprint"]))
    return {
        "mode": "dry-run",
        "eligible_issue_count": eligible,
        "duplicate_group_count": len(duplicate_groups),
        "duplicate_issue_count": duplicate_count,
        "groups": duplicate_groups,
    }


def _ensure_duplicate_label(requester: GithubRequester) -> None:
    labels = requester("GET", "/labels?per_page=100", None)
    if isinstance(labels, list) and any(
        isinstance(row, dict) and row.get("name") == DUPLICATE_LABEL for row in labels
    ):
        return
    requester(
        "POST",
        "/labels",
        {
            "name": DUPLICATE_LABEL,
            "color": "cfd3d7",
            "description": "Exact canonical duplicate of another authoritative Genesis issue",
        },
    )


def apply_reconciliation_plan(plan: dict, *, requester: GithubRequester, apply: bool = False) -> dict:
    """Apply a previously reviewed plan only when ``apply=True`` is explicit.

    GitHub Issues does not expose a ``duplicate`` state_reason through the REST
    Issues API. We therefore use the standard duplicate label plus an explicit
    canonical-primary comment and close with ``not_planned``.
    """

    groups = list(plan.get("groups") or [])
    if not apply:
        return {
            "mode": "dry-run",
            "would_close": sum(len(row.get("duplicate_issues") or []) for row in groups),
            "closed": [],
        }

    _ensure_duplicate_label(requester)
    closed: list[int] = []
    for group in groups:
        primary = int(group.get("primary_issue") or 0)
        fingerprint = str(group.get("fingerprint") or "")
        if primary <= 0 or not fingerprint.startswith("genesis-objective:"):
            continue
        for raw_number in group.get("duplicate_issues") or []:
            number = int(raw_number or 0)
            if number <= 0 or number == primary:
                continue
            requester(
                "POST",
                f"/issues/{number}/comments",
                {
                    "body": (
                        f"Closing as an exact canonical duplicate of #{primary}. "
                        f"Canonical fingerprint: `{fingerprint}`. All future work and retry evidence "
                        f"should remain on #{primary}."
                    )
                },
            )
            requester("POST", f"/issues/{number}/labels", {"labels": [DUPLICATE_LABEL]})
            requester(
                "PATCH",
                f"/issues/{number}",
                {"state": "closed", "state_reason": "not_planned"},
            )
            closed.append(number)

    return {"mode": "apply", "closed": closed, "closed_count": len(closed)}
