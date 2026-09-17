from __future__ import annotations

import json
import os

import agentic_lab_capability_first_dispatch as policy
import agentic_lab_recovery_dispatch as agentic


MAX_PARALLEL = int(os.environ.get("GENESIS_AGENTIC_MAX_PARALLEL", "4"))

if "qwen3_fallback" not in agentic.STRATEGIES:
    agentic.STRATEGIES = (*agentic.STRATEGIES, "qwen3_fallback")


def _parallel_routable_issues(repository: str, token: str) -> list[dict]:
    """Return all safely routable issues; per-issue labels prevent duplicates."""
    eligible: list[dict] = []
    for issue in policy._all_open_issues_fifo(repository, token):
        if not policy._actionable(issue):
            continue
        target = agentic.explicit_target(str(issue.get("body") or ""))
        if not agentic.safe_lane(target):
            continue
        eligible.append(issue)
    print(json.dumps({
        "selector": "bounded_parallel_autonomous",
        "eligible": [int(row.get("number") or 0) for row in eligible],
        "max_parallel": MAX_PARALLEL,
        "strategies": list(agentic.STRATEGIES),
    }, sort_keys=True))
    return eligible


def _active_issue_numbers(repository: str, token: str) -> list[int]:
    active: list[int] = []
    for issue in policy._all_open_issues_fifo(repository, token):
        if agentic.labels(issue) & agentic.ACTIVE_LABELS:
            number = int(issue.get("number") or 0)
            if number > 0:
                active.append(number)
    return active


def main() -> int:
    repository = os.environ.get("GITHUB_REPOSITORY", "").strip()
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if not repository or not token:
        raise RuntimeError("GITHUB_REPOSITORY and GITHUB_TOKEN are required")

    agentic.issue_comments = policy._all_issue_comments
    agentic.open_agentic_issues = _parallel_routable_issues
    agentic.next_strategy = policy._least_recently_used_strategy
    agentic.capability_gap_status = lambda _status: False
    agentic.pause_for_capability = policy._same_issue_pause

    all_open = policy._all_open_issues_fifo(repository, token)
    restored = policy._restore_agentic_visibility(repository, token, all_open)
    released = policy._release_legacy_waiting_dependencies(
        repository, token, policy._all_open_issues_fifo(repository, token)
    )

    active_before = _active_issue_numbers(repository, token)
    free_slots = max(0, MAX_PARALLEL - len(active_before))
    dispatched: list[dict] = []

    for _ in range(free_slots):
        result = agentic.reserve_and_dispatch(repository, token)
        if not isinstance(result, dict) or result.get("status") != "dispatched":
            break
        dispatched.append(result)

    result = {
        "status": "parallel_dispatch_complete",
        "max_parallel": MAX_PARALLEL,
        "active_before": active_before,
        "dispatched": [row.get("issue_number") for row in dispatched],
        "active_after": _active_issue_numbers(repository, token),
        "legacy_dependencies_released": released,
        "agentic_visibility_restored": restored,
        "strategies": list(agentic.STRATEGIES),
    }
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
