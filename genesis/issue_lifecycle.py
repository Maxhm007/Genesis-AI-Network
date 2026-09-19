from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Iterable


VERIFIED_LABEL = "genesis-verified"
SUPERSEDED_LABEL = "genesis-superseded"
SEALED_PREFIX = "genesis-closed-sealed-"
INFRA_QUARANTINE_MARKER = "<!-- genesis-agentic-infrastructure-quarantine -->"
SUCCESSOR_ROOT_RE = re.compile(r"<!-- genesis-unsolved-root:(\d+) -->")
SUCCESSOR_PARENT_RE = re.compile(r"<!-- genesis-unsolved-successor-of:(\d+) -->")
CAPABILITY_PARENT_RE = re.compile(r"<!-- genesis-capability-parent:(\d+) -->")
CAPABILITY_DEPENDENCY_RE = re.compile(r"<!-- genesis-agentic-capability-dependency:(\d+) -->")
CAPABILITY_RELEASE_RE = re.compile(r"<!-- genesis-agentic-capability-release:(\d+) -->")
PROBLEM_FP_RE = re.compile(r"^Genesis-Problem-Fingerprint:\s*([^\n]+)$", re.MULTILINE | re.IGNORECASE)
OCCURRENCE_FP_RE = re.compile(r"^Genesis-Occurrence-Fingerprint:\s*([^\n]+)$", re.MULTILINE | re.IGNORECASE)


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


def occurrence_fingerprint(issue: dict) -> str:
    match = OCCURRENCE_FP_RE.search(str(issue.get("body") or ""))
    return match.group(1).strip().lower() if match else ""


def _timestamp(issue: dict, *names: str) -> datetime | None:
    for name in names:
        value = str(issue.get(name) or "")
        if not value:
            continue
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            continue
    return None


def _verified_equivalent_predates_fix(issue: dict, other: dict) -> bool:
    occurrence = occurrence_fingerprint(issue)
    other_occurrence = occurrence_fingerprint(other)
    if occurrence and other_occurrence:
        return occurrence == other_occurrence
    created = _timestamp(issue, "created_at", "createdAt")
    resolved = _timestamp(other, "closed_at", "closedAt", "updated_at", "updatedAt")
    return created is not None and resolved is not None and created <= resolved


def root_issue_number(issue: dict) -> int | None:
    body = str(issue.get("body") or "")
    match = SUCCESSOR_ROOT_RE.search(body) or SUCCESSOR_PARENT_RE.search(body)
    if match:
        return int(match.group(1))
    return None


def capability_parent_numbers(issue: dict, comments: Iterable[dict] = ()) -> set[int]:
    text = str(issue.get("body") or "") + "\n" + "\n".join(str(row.get("body") or "") for row in comments)
    return {int(value) for value in CAPABILITY_PARENT_RE.findall(text)}



def authoritative_root_number(issue: dict) -> int:
    root = root_issue_number(issue)
    return int(root if root is not None else issue.get("number") or 0)


def family_id(issue: dict) -> str:
    root = authoritative_root_number(issue)
    return f"genesis-family:{root}" if root > 0 else ""


def _root_for_number(number: int, issues_by_number: dict[int, dict]) -> int:
    seen: set[int] = set()
    current = int(number)
    while current > 0 and current not in seen:
        seen.add(current)
        issue = issues_by_number.get(current)
        if issue is None:
            return current
        parent = root_issue_number(issue)
        if parent is None:
            return current
        current = int(parent)
    return int(number)


def family_ids_for_issue(
    issue: dict,
    issues_by_number: dict[int, dict],
    *,
    comments: Iterable[dict] = (),
) -> tuple[str, ...]:
    """Return every root family this record belongs to.

    Normal work belongs to one root family. Shared capability Issues may belong
    to several families through repeated genesis-capability-parent markers.
    """
    body = str(issue.get("body") or "")
    if "<!-- genesis-capability-work:" not in body:
        root = _root_for_number(authoritative_root_number(issue), issues_by_number)
        return (f"genesis-family:{root}",) if root > 0 else ()

    parents = capability_parent_numbers(issue, comments)
    roots = sorted({_root_for_number(parent, issues_by_number) for parent in parents if parent > 0})
    return tuple(f"genesis-family:{root}" for root in roots)


def released_dependency_numbers(issue: dict, comments: Iterable[dict] = ()) -> tuple[int, ...]:
    text = str(issue.get("body") or "") + "\n" + "\n".join(str(row.get("body") or "") for row in comments)
    return tuple(
        int(match.group(1))
        for line in text.splitlines()
        if (match := CAPABILITY_RELEASE_RE.search(line))
    )


def dependency_numbers(issue: dict, comments: Iterable[dict] = ()) -> tuple[int, ...]:
    text = str(issue.get("body") or "") + "\n" + "\n".join(str(row.get("body") or "") for row in comments)
    dependencies: list[int] = []
    active: set[int] = set()
    for line in text.splitlines():
        dep = CAPABILITY_DEPENDENCY_RE.search(line)
        if dep:
            number = int(dep.group(1))
            active.add(number)
            dependencies.append(number)
            continue
        release = CAPABILITY_RELEASE_RE.search(line)
        if release:
            active.discard(int(release.group(1)))
    return tuple(number for number in dependencies if number in active)


def family_status(
    root_number: int,
    issues_by_number: dict[int, dict],
    *,
    comments_by_number: dict[int, Iterable[dict]] | None = None,
) -> dict:
    """Build machine-readable authority/dependency status for one issue family."""
    comments_by_number = comments_by_number or {}
    root_number = _root_for_number(root_number, issues_by_number)
    root = issues_by_number.get(root_number)
    members: list[int] = []
    successors: list[int] = []
    capabilities: set[int] = set()
    relationships: list[dict] = []

    for number, issue in issues_by_number.items():
        resolved_root = _root_for_number(number, issues_by_number)
        if resolved_root == root_number:
            members.append(number)
            parent = root_issue_number(issue)
            if number == root_number:
                relationships.append({"issue": number, "kind": "root"})
            elif parent is not None:
                successors.append(number)
                relationships.append({
                    "issue": number,
                    "kind": "successor",
                    "predecessor": int(parent),
                    "root": root_number,
                })
        if "<!-- genesis-capability-work:" in str(issue.get("body") or ""):
            families = family_ids_for_issue(
                issue,
                issues_by_number,
                comments=comments_by_number.get(number, ()),
            )
            if f"genesis-family:{root_number}" in families:
                capabilities.add(number)
                relationships.append({
                    "issue": number,
                    "kind": "shared_capability",
                    "families": families,
                })

    current_authority = None
    dependencies: tuple[int, ...] = ()
    released: tuple[int, ...] = ()
    if root is not None:
        if not (is_closed(root) and is_verified(root)):
            current_authority = root_number
        root_comments = comments_by_number.get(root_number, ())
        dependencies = dependency_numbers(root, root_comments)
        released = released_dependency_numbers(root, root_comments)
        for dependency in dependencies:
            relationships.append({
                "issue": dependency,
                "kind": "capability_dependency",
                "parent": root_number,
                "status": "active",
            })
        for dependency in released:
            relationships.append({
                "issue": dependency,
                "kind": "capability_dependency",
                "parent": root_number,
                "status": "released",
            })

    chain: list[str] = [f"root:{root_number}"]
    for dependency in dependencies:
        chain.append(f"capability:{dependency}")
    if released:
        chain.append(f"resumed:{root_number}")

    return {
        "family_id": f"genesis-family:{root_number}",
        "root": root_number,
        "current_authority": current_authority,
        "members": tuple(sorted(set(members))),
        "successors": tuple(sorted(set(successors))),
        "capability_dependencies": tuple(sorted(set(dependencies))),
        "shared_capabilities": tuple(sorted(capabilities)),
        "released_capabilities": tuple(sorted(set(released))),
        "relationships": tuple(relationships),
        "chain": tuple(chain),
    }


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
        if root_issue is not None:
            if is_closed(root_issue) and is_verified(root_issue):
                return LifecycleDecision(
                    "close_superseded" if not is_closed(issue) else "keep_closed",
                    "verified_root_completed",
                    root,
                )
            # The root remains the single authority while unresolved. Legacy
            # successor/follow-up generations are historical evidence only.
            return LifecycleDecision(
                "close_superseded" if not is_closed(issue) else "keep_closed",
                "authoritative_root_unresolved",
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
                and _verified_equivalent_predates_fix(issue, other)
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
