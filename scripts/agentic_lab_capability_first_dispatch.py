from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import os

import agentic_lab_recovery_dispatch as agentic


STALE_RESERVATION_MINUTES = 100
SAME_ISSUE_MEMORY_PREFIX = "<!-- genesis-same-issue-recovery-memory:"
LEGACY_DEPENDENCY_RELEASE = "<!-- genesis-legacy-capability-dependency-released -->"


def _all_issue_comments(repository: str, token: str, number: int) -> list[dict]:
    """Read the complete issue history so retries use all earlier failure evidence."""
    rows: list[dict] = []
    for page in range(1, 101):
        batch = agentic.request(
            repository,
            token,
            "GET",
            f"/issues/{number}/comments?per_page=100&page={page}",
        ) or []
        if not isinstance(batch, list):
            raise RuntimeError("GitHub issue comments response was not a list")
        rows.extend(row for row in batch if isinstance(row, dict))
        if len(batch) < 100:
            break
    return rows


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


def _least_recently_used_strategy(comments: list[dict]) -> str:
    """Always return a strategy, preferring one not recently tried on this issue."""
    last_seen = {strategy: -1 for strategy in agentic.STRATEGIES}
    release_index = agentic._latest_release_index(comments)
    for index, row in enumerate(comments[release_index + 1 :], start=release_index + 1):
        body = str(row.get("body") or "")
        if not body.startswith(agentic.STRATEGY_MARKER_PREFIX):
            continue
        strategy = body[len(agentic.STRATEGY_MARKER_PREFIX) :].split("-->", 1)[0].strip()
        if strategy in last_seen:
            last_seen[strategy] = index
    return min(agentic.STRATEGIES, key=lambda strategy: (last_seen[strategy], agentic.STRATEGIES.index(strategy)))


def _clear_stale_reservations(repository: str, token: str, issues: list[dict]) -> list[int]:
    stale: list[int] = []
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=STALE_RESERVATION_MINUTES)
    for issue in issues:
        issue_labels = agentic.labels(issue)
        if not (issue_labels & agentic.ACTIVE_LABELS):
            continue
        number = int(issue.get("number") or 0)
        comments = agentic.issue_comments(repository, token, number)
        last_strategy = _latest_strategy_time(comments)
        if last_strategy is None or last_strategy > cutoff:
            continue
        for label in agentic.ACTIVE_LABELS | {"genesis-recovery-solver"}:
            agentic.remove_label(repository, token, number, label)
        agentic.request(
            repository,
            token,
            "POST",
            f"/issues/{number}/labels",
            {"labels": [agentic.AGENTIC_LABEL, "genesis-autonomous"]},
        )
        agentic.request(
            repository,
            token,
            "POST",
            f"/issues/{number}/comments",
            {
                "body": (
                    "<!-- genesis-stale-agentic-reservation-released -->\n"
                    f"Genesis released a stale repair reservation older than {STALE_RESERVATION_MINUTES} minutes. "
                    "The same Issue remains authoritative; its existing failure comments remain repair memory for the next attempt."
                )
            },
        )
        stale.append(number)
    return stale


def _release_legacy_waiting_dependencies(repository: str, token: str, issues: list[dict]) -> list[int]:
    """Retire the old parent->capability blocking rule without creating or deleting issues."""
    released: list[int] = []
    for issue in issues:
        issue_labels = agentic.labels(issue)
        if agentic.WAITING_CAPABILITY_LABEL not in issue_labels:
            continue
        number = int(issue.get("number") or 0)
        comments = agentic.issue_comments(repository, token, number)
        for label in (
            agentic.WAITING_CAPABILITY_LABEL,
            "genesis-blocked",
            "genesis-deferred",
            agentic.EXHAUSTED_LABEL,
            agentic.NEEDS_HUMAN_LABEL,
        ):
            agentic.remove_label(repository, token, number, label)
        agentic.request(
            repository,
            token,
            "POST",
            f"/issues/{number}/labels",
            {"labels": [agentic.AGENTIC_LABEL, "genesis-autonomous"]},
        )
        if not any(LEGACY_DEPENDENCY_RELEASE in str(row.get("body") or "") for row in comments):
            agentic.request(
                repository,
                token,
                "POST",
                f"/issues/{number}/comments",
                {
                    "body": (
                        f"{LEGACY_DEPENDENCY_RELEASE}\n"
                        "Genesis no longer creates or waits on a secondary capability Issue merely because this Issue was not solved. "
                        "This original Issue is authoritative again. Previous failure comments are retained as repair memory, and the next attempt must use that evidence with a different or least-recently-used strategy."
                    )
                },
            )
        released.append(number)
    return released


def _same_issue_pause(
    repository: str,
    token: str,
    issue: dict,
    comments: list[dict],
    target: str,
    reason: str,
) -> dict:
    """Safety fallback: record failure on the same issue; never create another issue."""
    number = int(issue.get("number") or 0)
    count = sum(
        1
        for row in comments
        if str(row.get("body") or "").startswith(SAME_ISSUE_MEMORY_PREFIX)
    ) + 1
    marker = f"{SAME_ISSUE_MEMORY_PREFIX}{count} -->"
    agentic.request(
        repository,
        token,
        "POST",
        f"/issues/{number}/comments",
        {
            "body": (
                f"{marker}\n"
                "**Genesis same-issue recovery memory**\n\n"
                f"- Target: `{target}`\n"
                f"- Latest blocker: `{reason or 'strategy_set_exhausted'}`\n"
                "- Decision: keep this Issue open and authoritative; do not create a successor or capability Issue.\n"
                "- Next attempt: read the full comment history and use the least-recently-used safe strategy, incorporating the recorded failure evidence."
            )
        },
    )
    for label in agentic.ACTIVE_LABELS | {
        agentic.WAITING_CAPABILITY_LABEL,
        agentic.NEEDS_HUMAN_LABEL,
        "genesis-blocked",
        "genesis-deferred",
        "genesis-recovery-solver",
        agentic.EXHAUSTED_LABEL,
    }:
        agentic.remove_label(repository, token, number, label)
    agentic.request(
        repository,
        token,
        "POST",
        f"/issues/{number}/labels",
        {"labels": [agentic.AGENTIC_LABEL, "genesis-autonomous"]},
    )
    return {"status": "same_issue_retry", "issue_number": number, "reason": reason}


def main() -> int:
    repository = os.environ.get("GITHUB_REPOSITORY", "").strip()
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if not repository or not token:
        raise RuntimeError("GITHUB_REPOSITORY and GITHUB_TOKEN are required")

    # Same-issue recovery policy:
    # 1. always read complete comments;
    # 2. never convert a repair failure into a new capability issue;
    # 3. choose the least-recently-used strategy from the accumulated issue history;
    # 4. retain one authoritative issue until a verified promotion closes it.
    agentic.issue_comments = _all_issue_comments
    agentic.next_strategy = _least_recently_used_strategy
    agentic.capability_gap_status = lambda _status: False
    agentic.pause_for_capability = _same_issue_pause

    all_agentic = agentic.open_agentic_issues(repository, token)
    stale = _clear_stale_reservations(repository, token, all_agentic)
    released = _release_legacy_waiting_dependencies(repository, token, all_agentic)
    if stale or released:
        all_agentic = agentic.open_agentic_issues(repository, token)

    active = [
        int(issue.get("number") or 0)
        for issue in all_agentic
        if agentic.labels(issue) & agentic.ACTIVE_LABELS
    ]
    if active:
        print(json.dumps({
            "status": "busy",
            "reason": "global_same_issue_repair_lock",
            "active_issues": active,
            "legacy_dependencies_released": released,
        }, sort_keys=True))
        return 0

    result = agentic.reserve_and_dispatch(repository, token)
    if isinstance(result, dict):
        result["policy"] = "same_issue_comment_memory"
        result["legacy_dependencies_released"] = released
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
