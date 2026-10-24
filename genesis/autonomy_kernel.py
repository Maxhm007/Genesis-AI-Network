from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Iterable


class IssueState(str, Enum):
    READY = "ready"
    ASSIGNED = "assigned"
    WORKING = "working"
    VALIDATING = "validating"
    BLOCKED = "blocked"
    VERIFIED = "verified"
    CLOSED = "closed"
    IGNORED = "ignored"


ACTIVE_LABELS = {
    "genesis-repair-in-progress",
    "genesis-claimed",
    "genesis-working",
    "genesis-verifying",
}
VALIDATING_LABELS = {"genesis-validating"}
BLOCKED_LABELS = {
    "genesis-blocked",
    "genesis-solver-exhausted",
    "genesis-deepseek-handoff-pending",
}
VERIFIED_LABELS = {"genesis-verified", "genesis-solved"}
IGNORED_LABELS = {
    "duplicate",
    "invalid",
    "wontfix",
    "genesis-superseded",
    "genesis-persistent",
    "performance-indicator",
}
AUTONOMY_LABEL = "genesis-autonomous"
HUMAN_LABELS = {"genesis-human-required", "human-intervention-required"}


@dataclass(frozen=True)
class IssueDecision:
    number: int
    state: str
    stalled: bool
    age_minutes: float
    action: str
    reason: str

    def as_dict(self) -> dict:
        return asdict(self)


def _labels(issue: dict) -> set[str]:
    result: set[str] = set()
    for value in issue.get("labels") or []:
        name = str(value.get("name") if isinstance(value, dict) else value or "").strip()
        if name:
            result.add(name)
    return result


def _parse_time(value: object) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def issue_state(issue: dict) -> IssueState:
    labels = _labels(issue)
    state = str(issue.get("state") or "open").lower()
    if state == "closed":
        return IssueState.CLOSED
    if labels & IGNORED_LABELS:
        return IssueState.IGNORED
    if labels & VERIFIED_LABELS:
        return IssueState.VERIFIED
    if labels & VALIDATING_LABELS:
        return IssueState.VALIDATING
    if labels & ACTIVE_LABELS:
        return IssueState.WORKING
    if labels & BLOCKED_LABELS:
        return IssueState.BLOCKED
    if AUTONOMY_LABEL in labels:
        return IssueState.READY
    return IssueState.IGNORED


def decide_issue(
    issue: dict,
    *,
    now: datetime | None = None,
    stalled_minutes: int = 90,
) -> IssueDecision:
    now = now or datetime.now(timezone.utc)
    number = int(issue.get("number") or 0)
    state = issue_state(issue)
    updated = _parse_time(issue.get("updated_at") or issue.get("created_at"))
    age = float("inf") if updated is None else max(0.0, (now - updated).total_seconds() / 60.0)
    stalled = (
        state in {IssueState.READY, IssueState.ASSIGNED, IssueState.BLOCKED}
        and age >= max(1, stalled_minutes)
    )

    if state == IssueState.CLOSED:
        action, reason = "none", "issue is closed"
    elif state == IssueState.IGNORED:
        action, reason = "none", "issue is outside the autonomous work queue"
    elif state == IssueState.VERIFIED:
        action, reason = "close_verified", "verified work should be reconciled to closure"
    elif state == IssueState.VALIDATING:
        action, reason = "await_independent_validation", "solver must not self-approve"
    elif state == IssueState.WORKING:
        action, reason = "continue_work", "an autonomous worker is active"
    elif stalled or state == IssueState.BLOCKED:
        action, reason = "recover_with_new_strategy", "issue is blocked or stale and needs a materially different strategy"
    else:
        action, reason = "dispatch_solver", "issue is ready for autonomous execution"

    return IssueDecision(
        number=number,
        state=state.value,
        stalled=stalled,
        age_minutes=round(age, 1),
        action=action,
        reason=reason,
    )


def summarize_issues(
    issues: Iterable[dict],
    *,
    now: datetime | None = None,
    stalled_minutes: int = 90,
) -> dict:
    decisions = [
        decide_issue(issue, now=now, stalled_minutes=stalled_minutes)
        for issue in issues
        if isinstance(issue, dict) and int(issue.get("number") or 0) > 0
    ]
    counts: dict[str, int] = {}
    for decision in decisions:
        counts[decision.state] = counts.get(decision.state, 0) + 1

    recovery = [d.number for d in decisions if d.action == "recover_with_new_strategy"]
    ready = [d.number for d in decisions if d.action == "dispatch_solver"]
    validating = [d.number for d in decisions if d.action == "await_independent_validation"]
    closeable = [d.number for d in decisions if d.action == "close_verified"]

    human_required = 0
    autonomous_open = 0
    for issue in issues:
        if not isinstance(issue, dict):
            continue
        labels = _labels(issue)
        if AUTONOMY_LABEL in labels and str(issue.get("state") or "open").lower() != "closed":
            autonomous_open += 1
            if labels & HUMAN_LABELS:
                human_required += 1

    denominator = max(1, autonomous_open)
    unattended_ratio = max(0.0, (autonomous_open - human_required) / denominator)

    return {
        "state_counts": counts,
        "ready_issue_numbers": ready,
        "recovery_issue_numbers": recovery,
        "validating_issue_numbers": validating,
        "verified_to_close_issue_numbers": closeable,
        "autonomous_open_count": autonomous_open,
        "human_intervention_required_count": human_required,
        "unattended_open_ratio": round(unattended_ratio, 4),
        "decisions": [d.as_dict() for d in decisions],
        "principle": "Green workflows are evidence of execution, not proof of outcome. Issue state and verified closure define progress.",
    }
