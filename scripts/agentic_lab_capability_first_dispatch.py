from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import os

import agentic_lab_recovery_dispatch as agentic
from capability_issue_priority_dispatch import quarantined_for_current_generation
from requeue_exhausted_issues import engine_generation


STALE_RESERVATION_MINUTES = 100


def _is_capability(issue: dict) -> bool:
    return agentic.CAPABILITY_WORK_PREFIX in str(issue.get("body") or "")


def _latest_strategy_time(comments: list[dict]) -> datetime | None:
    for row in reversed(comments):
        body = str(row.get("body") or "")
        if not body.startswith(agentic.STRATEGY_MARKER_PREFIX):
            continue
        raw = str(row.get("created_at") or "").strip()
        if not raw:
            return None
        try:
            return datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


def _clear_stale_capability_reservations(repository: str, token: str, issues: list[dict]) -> list[int]:
    stale: list[int] = []
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=STALE_RESERVATION_MINUTES)
    for issue in issues:
        if not _is_capability(issue):
            continue
        issue_labels = agentic.labels(issue)
        if not (issue_labels & agentic.ACTIVE_LABELS):
            continue
        number = int(issue.get("number") or 0)
        comments = agentic.issue_comments(repository, token, number)
        last_strategy = _latest_strategy_time(comments)
        if last_strategy is None or last_strategy > cutoff:
            continue
        for label in agentic.ACTIVE_LABELS | {"genesis-autonomous", "genesis-recovery-solver"}:
            agentic.remove_label(repository, token, number, label)
        agentic.request(
            repository,
            token,
            "POST",
            f"/issues/{number}/labels",
            {"labels": [agentic.AGENTIC_LABEL, agentic.EXHAUSTED_LABEL]},
        )
        agentic.request(
            repository,
            token,
            "POST",
            f"/issues/{number}/comments",
            {
                "body": (
                    "<!-- genesis-stale-capability-reservation-released -->\n"
                    f"Genesis released a stale capability repair reservation older than {STALE_RESERVATION_MINUTES} minutes. "
                    "The same Issue remains authoritative and will be retried through the bounded capability-first lifecycle."
                )
            },
        )
        stale.append(number)
    return stale


def prioritized_agentic_issues(repository: str, token: str) -> list[dict]:
    current_generation = engine_generation()
    capability: list[dict] = []
    ordinary: list[dict] = []
    quarantined: list[int] = []

    for issue in agentic.open_agentic_issues(repository, token):
        if not _is_capability(issue):
            ordinary.append(issue)
            continue
        number = int(issue.get("number") or 0)
        comments = agentic.issue_comments(repository, token, number)
        if quarantined_for_current_generation(comments, current_generation):
            quarantined.append(number)
            continue
        capability.append(issue)

    print(json.dumps({
        "selector": "capability_first",
        "repair_engine_generation": current_generation,
        "eligible_capability_issues": [int(row.get("number") or 0) for row in capability],
        "quarantined_capability_issues": quarantined,
        "ordinary_agentic_issues": len(ordinary),
    }, sort_keys=True))
    return capability + ordinary


def main() -> int:
    repository = os.environ.get("GITHUB_REPOSITORY", "").strip()
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if not repository or not token:
        raise RuntimeError("GITHUB_REPOSITORY and GITHUB_TOKEN are required")

    original_selector = agentic.open_agentic_issues
    original_pause = agentic.pause_for_capability

    all_agentic = original_selector(repository, token)
    stale = _clear_stale_capability_reservations(repository, token, all_agentic)
    if stale:
        all_agentic = original_selector(repository, token)

    active_capabilities = [
        int(issue.get("number") or 0)
        for issue in all_agentic
        if _is_capability(issue) and (agentic.labels(issue) & agentic.ACTIVE_LABELS)
    ]
    if active_capabilities:
        print(json.dumps({
            "status": "busy",
            "reason": "global_capability_lock",
            "active_capability_issues": active_capabilities,
        }, sort_keys=True))
        return 0

    def _selector(repo: str, tok: str) -> list[dict]:
        current_generation = engine_generation()
        capability: list[dict] = []
        ordinary: list[dict] = []
        quarantined: list[int] = []
        for issue in original_selector(repo, tok):
            if not _is_capability(issue):
                ordinary.append(issue)
                continue
            number = int(issue.get("number") or 0)
            comments = agentic.issue_comments(repo, tok, number)
            if quarantined_for_current_generation(comments, current_generation):
                quarantined.append(number)
                continue
            capability.append(issue)
        print(json.dumps({
            "selector": "capability_first",
            "repair_engine_generation": current_generation,
            "eligible_capability_issues": [int(row.get("number") or 0) for row in capability],
            "quarantined_capability_issues": quarantined,
            "ordinary_agentic_issues": len(ordinary),
        }, sort_keys=True))
        return capability + ordinary

    def _bounded_capability_pause(repo: str, tok: str, issue: dict, comments: list[dict], target: str, reason: str) -> dict:
        if not _is_capability(issue):
            return original_pause(repo, tok, issue, comments, target, reason)
        number = int(issue.get("number") or 0)
        release_count = sum(
            1 for row in comments
            if str(row.get("body") or "").startswith(agentic.CAPABILITY_RELEASE_PREFIX)
        )
        marker = f"{agentic.CAPABILITY_RELEASE_PREFIX}{release_count + 1} -->"
        agentic.request(
            repo,
            tok,
            "POST",
            f"/issues/{number}/comments",
            {
                "body": (
                    f"{marker}\n"
                    "Genesis exhausted the current materially different capability-repair strategy set. "
                    "Instead of terminalizing as needs-human or creating a duplicate capability Issue, the same authoritative capability Issue is recycled for a fresh bounded strategy generation."
                )
            },
        )
        for label in agentic.ACTIVE_LABELS | {agentic.NEEDS_HUMAN_LABEL, "genesis-deferred", "genesis-recovery-solver"}:
            agentic.remove_label(repo, tok, number, label)
        agentic.request(
            repo,
            tok,
            "POST",
            f"/issues/{number}/labels",
            {"labels": [agentic.AGENTIC_LABEL, agentic.EXHAUSTED_LABEL, "genesis-autonomous"]},
        )
        return {"status": "capability_recycled", "issue_number": number, "reason": reason}

    agentic.open_agentic_issues = _selector
    agentic.pause_for_capability = _bounded_capability_pause
    agentic.reserve_and_dispatch(repository, token)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
