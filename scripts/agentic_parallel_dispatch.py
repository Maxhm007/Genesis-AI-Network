from __future__ import annotations

from datetime import datetime, timezone
import json
import os
import re

try:
    from scripts import agentic_lab_capability_first_dispatch as policy
    from scripts import agentic_lab_recovery_dispatch as agentic
except ModuleNotFoundError:
    # Direct execution via "python scripts/agentic_parallel_dispatch.py" places
    # scripts/ itself on sys.path; package-style imports are then unavailable.
    import agentic_lab_capability_first_dispatch as policy
    import agentic_lab_recovery_dispatch as agentic
from genesis.issue_governor import issue_value_score


MAX_PARALLEL = int(os.environ.get("GENESIS_AGENTIC_MAX_PARALLEL", "4"))

if "qwen3_fallback" not in agentic.STRATEGIES:
    agentic.STRATEGIES = (*agentic.STRATEGIES, "qwen3_fallback")


def _created_at(issue: dict) -> datetime:
    raw = str(issue.get("created_at") or issue.get("createdAt") or "").strip()
    try:
        value = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return datetime(1970, 1, 1, tzinfo=timezone.utc)
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _severity(issue_labels: set[str]) -> str:
    lowered = {label.lower() for label in issue_labels}
    if lowered & {"critical", "severity-critical", "security-critical"}:
        return "critical"
    if lowered & {"high", "severity-high", "priority-high"}:
        return "high"
    if lowered & {"low", "severity-low", "priority-low"}:
        return "low"
    return "medium"


def _retry_depth(comments: list[dict]) -> int:
    markers = 0
    for row in comments:
        text = str(row.get("body") or "").lower()
        if (
            "genesis-agentic-strategy-result:" in text
            or "genesis-requeue-engine:" in text
            or "repair attempt" in text
            or "retry" in text
        ):
            markers += 1
    return markers


def _dependency_unlock_counts(
    issues: list[dict],
    comments_by_issue: dict[int, list[dict]],
) -> dict[int, int]:
    counts: dict[int, set[int]] = {}
    pattern = re.compile(r"genesis-capability-dependency:(\d+)")
    for issue in issues:
        parent = int(issue.get("number") or 0)
        corpus = [str(issue.get("body") or "")]
        corpus.extend(str(row.get("body") or "") for row in comments_by_issue.get(parent, []))
        for text in corpus:
            for match in pattern.finditer(text):
                dependency = int(match.group(1))
                if dependency > 0 and dependency != parent:
                    counts.setdefault(dependency, set()).add(parent)
    return {number: len(parents) for number, parents in counts.items()}


def _score_issue(
    issue: dict,
    comments: list[dict],
    *,
    unlock_count: int,
    now: datetime,
) -> dict:
    labels = agentic.labels(issue)
    age_hours = max(0.0, (now - _created_at(issue).astimezone(timezone.utc)).total_seconds() / 3600.0)
    retry_depth = _retry_depth(comments)
    owner_priority = 1.0 if labels & {"owner-priority", "owner_priority", "user-priority"} else 0.0
    is_capability = "genesis-capability-gap" in labels or "<!-- genesis-capability-work:" in str(issue.get("body") or "")
    reuse_value = 0.95 if is_capability else (0.85 if labels & {"genesis-capability", "capability-blocker"} else 0.65)
    success_probability = max(0.25, 0.9 - 0.07 * retry_depth)
    value = issue_value_score(
        severity=_severity(labels),
        blocked_issues=unlock_count,
        age_hours=age_hours,
        reuse_value=reuse_value,
        owner_priority=owner_priority,
        retry_depth=retry_depth,
        success_probability=success_probability,
    )
    return {
        "number": int(issue.get("number") or 0),
        "score": value.score,
        "breakdown": value.breakdown,
        "unlock_count": unlock_count,
        "retry_depth": retry_depth,
        "created_at": _created_at(issue).isoformat(),
    }


def _parallel_routable_issues(repository: str, token: str) -> list[dict]:
    """Return safely routable issues ordered by deterministic operational value."""
    all_open = policy._all_open_issues_fifo(repository, token)
    eligible: list[dict] = []
    comments_by_issue: dict[int, list[dict]] = {
        int(issue.get("number") or 0): policy._all_issue_comments(
            repository, token, int(issue.get("number") or 0)
        )
        for issue in all_open
        if int(issue.get("number") or 0) > 0
    }
    for issue in all_open:
        if not policy._actionable(issue):
            continue
        number = int(issue.get("number") or 0)
        if policy._infra_quarantined(repository, token, number):
            continue
        issue_labels = agentic.labels(issue)
        target = agentic.explicit_target(str(issue.get("body") or ""))
        if not agentic.safe_lane(target):
            continue
        eligible.append(issue)

    unlock_counts = _dependency_unlock_counts(all_open, comments_by_issue)
    now = datetime.now(timezone.utc)
    scored = [
        (
            issue,
            _score_issue(
                issue,
                comments_by_issue.get(int(issue.get("number") or 0), []),
                unlock_count=unlock_counts.get(int(issue.get("number") or 0), 0),
                now=now,
            ),
        )
        for issue in eligible
    ]
    scored.sort(
        key=lambda row: (
            0 if "genesis-solver-exhausted" in agentic.labels(row[0]) else 1,
            -float(row[1]["score"]),
            row[1]["created_at"],
            int(row[1]["number"]),
        )
    )
    ordered = [row[0] for row in scored]
    print(json.dumps({
        "selector": "bounded_parallel_exhausted_first_value_priority",
        "eligible": [int(row.get("number") or 0) for row in ordered],
        "ranked_candidates": [row[1] for row in scored[:10]],
        "max_parallel": MAX_PARALLEL,
        "strategies": list(agentic.STRATEGIES),
    }, sort_keys=True))
    return ordered


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

    # Do not override capability escalation here. When every materially different
    # repair strategy reports a capability blocker, the canonical Agentic recovery
    # layer must pause the parent and create/reuse one bounded capability Issue.
    # The former same-Issue override forced endless retries and could never converge.
    all_open = policy._all_open_issues_fifo(repository, token)
    restored = policy._restore_agentic_visibility(repository, token, all_open)
    released = agentic.release_ready_capability_dependencies(repository, token)

    # Reconcile/decompose multiple architecture Issues per recovery pass. One
    # stale inferred target must not consume the whole cycle while newer work
    # remains hidden. Keep this bounded to avoid an unbounded controller loop.
    decomposition_steps: list[dict] = []
    seen_decomposition_actions: set[tuple[str, int, str]] = set()
    for _ in range(12):
        step = policy._decompose_oldest_issue(repository, token, all_open)
        key = (
            str(step.get("status") or ""),
            int(step.get("issue_number") or 0),
            str(step.get("target") or step.get("previous_target") or ""),
        )
        if key in seen_decomposition_actions:
            break
        seen_decomposition_actions.add(key)
        decomposition_steps.append(step)
        if step.get("status") not in {"decomposed", "retargeted", "target_revoked"}:
            break
        all_open = policy._all_open_issues_fifo(repository, token)
    decomposition = decomposition_steps[-1] if decomposition_steps else {"status": "idle"}

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
        "capability_escalation": "enabled",
        "agentic_visibility_restored": restored,
        "decomposition": decomposition,
        "decomposition_steps": decomposition_steps,
        "strategies": list(agentic.STRATEGIES),
    }
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
