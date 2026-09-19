from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable


VERIFIED_LABEL = "genesis-verified"
SUPERSEDED_LABEL = "genesis-superseded"
SEALED_PREFIX = "genesis-closed-sealed-"
INFRA_QUARANTINE_MARKER = "<!-- genesis-agentic-infrastructure-quarantine -->"
SUCCESSOR_ROOT_RE = re.compile(r"<!-- genesis-unsolved-root:(\d+) -->")
SUCCESSOR_PARENT_RE = re.compile(r"<!-- genesis-unsolved-successor-of:(\d+) -->")
CAPABILITY_PARENT_RE = re.compile(r"<!-- genesis-capability-parent:(\d+) -->")
PROBLEM_FP_RE = re.compile(r"^Genesis-Problem-Fingerprint:\s*([^\n]+)$", re.MULTILINE | re.IGNORECASE)


@dataclass(frozen=True)
class LifecycleDecision:
    action: str
    reason: str
    reference_issue: int | None = None


def labels(issue: dict) -> set[str]:
    values = issue.get("labels") or []
    result: set[str] = set()
    for value in values:
        if isinstance(value, dict):
            name = str(value.get("name") or "").strip()
        else:
            name = str(value or "").strip()
        if name:
            result.add(name)
    return result


def is_closed(issue: dict) -> bool:
    return str(issue.get("state") or "").lower() == "closed"


def is_verified(issue: dict) -> bool:
    return VERIFIED_LABEL in labels(issue)


def is_sealed(issue: dict) -> bool:
    return any(name.startswith(SEALED_PREFIX) for name in labels(issue))


def is_superseded(issue: dict) -> bool:
    issue_labels = labels(issue)
    return SUPERSEDED_LABEL in issue_labels or str(issue.get("state_reason") or "").lower() == "duplicate"


def problem_fingerprint(issue: dict) -> str:
    match = PROBLEM_FP_RE.search(str(issue.get("body") or ""))
    return match.group(1).strip().lower() if match else ""


def root_issue_number(issue: dict) -> int | None:
    body = str(issue.get("body") or "")
    match = SUCCESSOR_ROOT_RE.search(body) or SUCCESSOR_PARENT_RE.search(body)
    if match:
        return int(match.group(1))
    return None


def capability_parent_numbers(issue: dict, comments: Iterable[dict] = ()) -> set[int]:
    text = str(issue.get("body") or "") + "\n" + "\n".join(str(row.get("body") or "") for row in comments)
    return {int(value) for value in CAPABILITY_PARENT_RE.findall(text)}


def local_claim_block_reason(issue: dict, comments: Iterable[dict] = ()) -> str:
    if is_closed(issue):
        return "closed"
    if is_verified(issue):
        return "verified"
    if is_superseded(issue):
        return "superseded"
    if any(INFRA_QUARANTINE_MARKER in str(row.get("body") or "") for row in comments):
        return "infrastructure_quarantine"
    return ""


def lifecycle_decision(
    issue: dict,
    issues_by_number: dict[int, dict],
    *,
    comments: Iterable[dict] = (),
) -> LifecycleDecision:
    """Return the authoritative lifecycle action from current repository state.

    Current verified repository state wins over stale retry/reconciler history.
    This function never decides that implementation acceptance passed by itself;
    it only reconciles authority, duplicate identity, dependency liveness, and
    stale closure/reopen behavior.
    """
    number = int(issue.get("number") or 0)
    issue_labels = labels(issue)

    if is_superseded(issue):
        return LifecycleDecision("keep_closed" if is_closed(issue) else "close_superseded", "explicitly_superseded")

    root = root_issue_number(issue)
    if root:
        root_issue = issues_by_number.get(root)
        if root_issue and is_closed(root_issue) and is_verified(root_issue):
            return LifecycleDecision(
                "close_superseded" if not is_closed(issue) else "keep_closed",
                "verified_root_completed",
                root,
            )

    fp = problem_fingerprint(issue)
    if fp:
        for other_number, other in issues_by_number.items():
            if other_number == number:
                continue
            if (
                problem_fingerprint(other) == fp
                and is_closed(other)
                and is_verified(other)
            ):
                return LifecycleDecision(
                    "close_duplicate" if not is_closed(issue) else "keep_closed",
                    "equivalent_problem_verified",
                    other_number,
                )

    if "<!-- genesis-capability-work:" in str(issue.get("body") or ""):
        parents = capability_parent_numbers(issue, comments)
        live_parents = [
            parent
            for parent in parents
            if parent in issues_by_number and not is_closed(issues_by_number[parent])
        ]
        if parents and not live_parents:
            return LifecycleDecision(
                "close_superseded" if not is_closed(issue) else "keep_closed",
                "no_live_capability_parent",
            )

    if is_closed(issue):
        if is_verified(issue) or is_sealed(issue):
            return LifecycleDecision("keep_closed", "verified_or_sealed")
        # Closed duplicates/superseded work must never be revived because of
        # stale solver labels. Reopen only a still-authoritative root task.
        if root is None and "genesis-task" in issue_labels:
            return LifecycleDecision("reopen", "authoritative_unverified_root")
        return LifecycleDecision("keep_closed", "non_authoritative_closed_work")

    return LifecycleDecision("keep_open", "authoritative_open_work")
