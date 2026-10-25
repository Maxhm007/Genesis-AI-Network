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
from genesis.autonomy_kernel import decide_issue
from genesis.issue_governor import issue_value_score


# Genesis runs a bounded parallel worker pool. Development and recovery lanes
# are independently configurable so normal work can continue while automation
# or capability failures are repaired. Issues targeting the same file/module
# are never admitted together, so parallelism cannot create same-target edits.
#
# Defaults: 4 development + 2 recovery workers = 6 issue workers. The Action
# Repair Worker is intentionally separate and can run alongside this pool.
def _positive_int_env(name: str, default: int, *, maximum: int = 12) -> int:
    raw = os.environ.get(name, "").strip()
    try:
        value = int(raw) if raw else default
    except ValueError:
        value = default
    return max(1, min(value, maximum))


DEVELOPMENT_SLOTS = _positive_int_env("GENESIS_AGENTIC_DEVELOPMENT_SLOTS", 4)
RECOVERY_SLOTS = _positive_int_env("GENESIS_AGENTIC_RECOVERY_SLOTS", 2)
MAX_PARALLEL = min(
    _positive_int_env("GENESIS_AGENTIC_MAX_PARALLEL", 6),
    DEVELOPMENT_SLOTS + RECOVERY_SLOTS,
)
SEQUENTIAL_FOCUS_LABEL = "genesis-sequential-focus"  # deprecated compatibility label

RECOVERY_LABELS = {
    "genesis-solver-exhausted",
    "genesis-capability-gap",
    "genesis-blocked",
    "genesis-needs-routing",
    "genesis-waiting-capability",
}

KERNEL_DISPATCH_ACTIONS = {"dispatch_solver", "recover_with_new_strategy"}

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


def _kernel_decomposition_order(issues: list[dict]) -> list[dict]:
    """Prioritize targetless work the Autonomy Kernel has already approved.

    Before this guard, a kernel-approved issue could be correctly classified as
    dispatch/recovery work and then silently disappear because the generic
    selector requires a safe target. Put those issues at the front of the
    decomposition pass so they receive a deterministic repository target first.

    Agentic-Lab-owned recovery work is preferred, then other recovery work, then
    fresh dispatchable work. Original FIFO order is preserved within each class.
    """
    now = datetime.now(timezone.utc)
    ranked: list[tuple[int, int, dict]] = []
    remainder: list[dict] = []
    for index, issue in enumerate(issues):
        if not policy._actionable(issue):
            remainder.append(issue)
            continue
        target = agentic.explicit_target(str(issue.get("body") or ""))
        if agentic.safe_lane(target):
            remainder.append(issue)
            continue
        decision = decide_issue(issue, now=now)
        if decision.action not in KERNEL_DISPATCH_ACTIONS:
            remainder.append(issue)
            continue
        labels = agentic.labels(issue)
        owned = 0 if agentic.AGENTIC_LABEL in labels else 1
        action_rank = 0 if decision.action == "recover_with_new_strategy" else 1
        ranked.append((owned * 10 + action_rank, index, issue))

    ranked.sort(key=lambda row: (row[0], row[1]))
    prioritized = [row[2] for row in ranked]
    prioritized_numbers = {int(row.get("number") or 0) for row in prioritized}
    return prioritized + [
        issue for issue in remainder
        if int(issue.get("number") or 0) not in prioritized_numbers
    ]


def _first_kernel_targetless_issue(issues: list[dict]) -> dict | None:
    """Return the highest-priority targetless issue the Kernel already approved."""
    ordered = _kernel_decomposition_order(issues)
    now = datetime.now(timezone.utc)
    for issue in ordered:
        if not policy._actionable(issue):
            continue
        target = agentic.explicit_target(str(issue.get("body") or ""))
        if agentic.safe_lane(target):
            continue
        decision = decide_issue(issue, now=now)
        if decision.action in KERNEL_DISPATCH_ACTIONS:
            return issue
    return None


def _decompose_kernel_priority_issue(repository: str, token: str, issues: list[dict]) -> dict | None:
    """Route one Kernel-approved targetless issue before generic FIFO routing."""
    issue = _first_kernel_targetless_issue(issues)
    if issue is None:
        return None
    number = int(issue.get("number") or 0)
    result = policy._decompose_oldest_issue(repository, token, [issue])
    if not isinstance(result, dict):
        result = {"status": "routing_failed", "issue_number": number, "reason": "invalid_decomposer_result"}
    status = str(result.get("status") or "")
    if status in {"decomposed", "retargeted", "target_revoked", "routing_released"}:
        return result

    reason = str(result.get("reason") or "kernel_priority_targetless_issue_not_routed")
    marker = "<!-- genesis-kernel-routing-failure -->"
    comments = agentic.issue_comments(repository, token, number)
    if not any(marker in str(row.get("body") or "") for row in comments):
        agentic.request(
            repository,
            token,
            "POST",
            f"/issues/{number}/comments",
            {"body": (
                f"{marker}\n"
                "**Genesis Kernel routing failure**\n\n"
                "Autonomy Kernel approved this Issue for dispatch/recovery, but target decomposition did not produce a safe target. "
                f"Reason: `{reason}`. The Issue remains authoritative and must be retried after routing repair; it was not silently skipped."
            )},
        )
    return {
        "status": "routing_failed",
        "issue_number": number,
        "reason": reason,
    }

def _parallel_routable_issues(
    repository: str,
    token: str,
    *,
    all_open: list[dict] | None = None,
    comments_cache: dict[int, list[dict]] | None = None,
) -> list[dict]:
    """Return safely routable issues ordered by deterministic operational value.

    A controller pass may call this selector several times while filling worker
    lanes. Reuse the same issue snapshot/comment cache to avoid multiplying
    GitHub API reads by the number of parallel lanes.
    """
    all_open = list(all_open) if all_open is not None else policy._all_open_issues_fifo(repository, token)
    comments_by_issue = comments_cache if comments_cache is not None else {}
    eligible: list[dict] = []
    kernel_actions: dict[int, str] = {}
    now = datetime.now(timezone.utc)
    for issue in all_open:
        if not policy._actionable(issue):
            continue
        number = int(issue.get("number") or 0)
        kernel_decision = decide_issue(issue, now=now)
        kernel_actions[number] = kernel_decision.action
        if kernel_decision.action not in KERNEL_DISPATCH_ACTIONS:
            continue
        target = agentic.explicit_target(str(issue.get("body") or ""))
        if not agentic.safe_lane(target):
            continue
        if number not in comments_by_issue:
            comments_by_issue[number] = policy._all_issue_comments(repository, token, number)
        quarantine_marker = (
            f"{policy.INFRA_QUARANTINE_MARKER[:-4]}:"
            f"{agentic.recovery_engine_generation()} -->"
        )
        if any(
            quarantine_marker in str(row.get("body") or "")
            for row in comments_by_issue[number]
        ):
            continue
        eligible.append(issue)

    unlock_counts = _dependency_unlock_counts(all_open, comments_by_issue)
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
            0 if (
                "genesis-capability-gap" in agentic.labels(row[0])
                or "<!-- genesis-capability-work:" in str(row[0].get("body") or "")
            ) else (1 if "genesis-solver-exhausted" in agentic.labels(row[0]) else 2),
            -int(row[1]["unlock_count"]),
            -float(row[1]["score"]),
            row[1]["created_at"],
            int(row[1]["number"]),
        )
    )
    ordered = [row[0] for row in scored]
    print(json.dumps({
        "selector": "bounded_parallel_capability_first_exhausted_second",
        "eligible": [int(row.get("number") or 0) for row in ordered],
        "ranked_candidates": [row[1] for row in scored[:10]],
        "max_parallel": MAX_PARALLEL,
        "strategies": list(agentic.STRATEGIES),
        "kernel_actions": {str(number): action for number, action in sorted(kernel_actions.items())},
    }, sort_keys=True))
    return ordered


def _is_recovery_issue(issue: dict) -> bool:
    # The kernel is the canonical state interpreter. A real GitHub issue always
    # carries updated_at; when it declares the issue stalled/blocked, Recovery
    # owns the next attempt even if legacy labels have not caught up yet.
    if issue.get("updated_at"):
        decision = decide_issue(issue, now=datetime.now(timezone.utc))
        if decision.action == "recover_with_new_strategy":
            return True
        if decision.action not in KERNEL_DISPATCH_ACTIONS:
            return False

    # Compatibility fallback for synthetic/unit-test records that omit GitHub
    # timestamps, plus capability/action-failure families that are intrinsically
    # recovery work.
    labels = agentic.labels(issue)
    title = str(issue.get("title") or "").strip().lower()
    body = str(issue.get("body") or "").lower()
    return bool(
        labels & RECOVERY_LABELS
        or title.startswith("genesis action failure:")
        or "action-failure-watcher" in body
        or "<!-- genesis-capability-work:" in body
    )


def _lane_routable_issues(
    repository: str,
    token: str,
    *,
    all_open: list[dict] | None = None,
    comments_cache: dict[int, list[dict]] | None = None,
    excluded_issue_numbers: set[int] | None = None,
) -> list[dict]:
    """Return work for the first free bounded lane without target collisions.

    Development work and recovery/capability work use separate configurable
    lane pools so broken automation cannot consume all development capacity.
    Every active target acts as a lock: another issue with that exact target is
    skipped until the owner leaves its active/validation state.
    """
    all_open = list(all_open) if all_open is not None else policy._all_open_issues_fifo(repository, token)
    excluded = {int(number) for number in (excluded_issue_numbers or set()) if int(number) > 0}
    active_labels = (set(agentic.ACTIVE_LABELS) - {"genesis-deepseek-handoff-pending"}) | {
        "genesis-claimed",
        "genesis-deepseek-working",
    }
    active = [issue for issue in all_open if agentic.labels(issue) & active_labels]

    active_recovery = sum(1 for issue in active if _is_recovery_issue(issue))
    active_development = sum(1 for issue in active if not _is_recovery_issue(issue))
    recovery_free = max(0, RECOVERY_SLOTS - active_recovery)
    development_free = max(0, DEVELOPMENT_SLOTS - active_development)

    locked_targets = {
        agentic.explicit_target(str(issue.get("body") or ""))
        for issue in active
        if agentic.explicit_target(str(issue.get("body") or ""))
    }

    ordered = _parallel_routable_issues(
        repository,
        token,
        all_open=all_open,
        comments_cache=comments_cache,
    )
    recovery_candidates: list[dict] = []
    development_candidates: list[dict] = []
    seen_targets = set(locked_targets)

    for issue in ordered:
        number = int(issue.get("number") or 0)
        if number in excluded:
            continue
        if agentic.labels(issue) & active_labels:
            continue
        target = agentic.explicit_target(str(issue.get("body") or ""))
        if target and target in seen_targets:
            continue
        if target:
            seen_targets.add(target)
        if _is_recovery_issue(issue):
            recovery_candidates.append(issue)
        else:
            development_candidates.append(issue)

    # Service a recovery lane first when it is free, then normal development.
    # reserve_and_dispatch() is called repeatedly; after each reservation the
    # freshly applied active label makes the next call select another lane.
    if recovery_free and development_free:
        return recovery_candidates[:recovery_free] + development_candidates[:development_free]
    if recovery_free:
        return recovery_candidates[:recovery_free]
    if development_free:
        return development_candidates[:development_free]
    return []


def _sequential_routable_issues(repository: str, token: str) -> list[dict]:
    """Compatibility alias for older callers; scheduling is no longer global-serial."""
    return _lane_routable_issues(repository, token)


def _live_agentic_worker_exists(repository: str, token: str) -> bool:
    """Return whether the single sequential lane has a queued/running worker."""
    for status in ("queued", "in_progress", "waiting", "pending", "requested"):
        try:
            payload = agentic.request(
                repository,
                token,
                "GET",
                f"/actions/runs?status={status}&per_page=100",
            )
        except Exception:
            # Fail closed: never clear a reservation when Actions visibility is
            # unavailable, because that could create duplicate workers.
            return True
        runs = payload.get("workflow_runs", []) if isinstance(payload, dict) else []
        for run in runs:
            # Push invocations only validate the baseline; they own no issue.
            if run.get("event") != "workflow_dispatch":
                continue
            # Actions exposes run-name in `name` (for example Issue #867 —
            # evidence_first), so recognize the canonical workflow path too.
            workflow_path = str(run.get("path") or "").split("@", 1)[0]
            if workflow_path in {
                ".github/workflows/genesis-agentic-strategy-worker.yml",
                ".github/workflows/genesis-deepseek-agentic-solver.yml",
                ".github/workflows/genesis-bounded-repair-worker.yml",
            } or str(run.get("name") or "") in {
                "Genesis Agentic Strategy Worker",
                "Genesis DeepSeek Agentic Solver",
                "Genesis Bounded Repair Worker",
            }:
                return True
    return False


def _reclaim_stale_sequential_reservation(repository: str, token: str) -> list[int]:
    """Release a focus reservation only when no solver worker exists at all."""
    if _live_agentic_worker_exists(repository, token):
        return []
    reclaimed: list[int] = []
    for issue in policy._all_open_issues_fifo(repository, token):
        labels = agentic.labels(issue)
        if SEQUENTIAL_FOCUS_LABEL not in labels:
            continue
        if not (labels & set(agentic.ACTIVE_LABELS)):
            continue
        number = int(issue.get("number") or 0)
        if number <= 0:
            continue
        for stale in (
            "genesis-repair-in-progress",
            "genesis-validating",
            "genesis-working",
            "genesis-verifying",
            "genesis-deepseek-handoff-pending",
            "genesis-claimed",
            "genesis-deepseek-working",
        ):
            agentic.remove_label(repository, token, number, stale)
        reclaimed.append(number)
    return reclaimed



def _reclaim_orphaned_reservations(
    repository: str, token: str, issues: list[dict], *, stale_minutes: int = 90
) -> list[int]:
    """Release aged worker labels only when GitHub confirms no live solver.

    An unavailable Actions API fails closed via _live_agentic_worker_exists.
    No unverified issue is closed and no capability/deferred hold is removed.
    """
    active_labels = (set(agentic.ACTIVE_LABELS) - {"genesis-deepseek-handoff-pending"}) | {
        "genesis-claimed", "genesis-deepseek-working",
    }
    now = datetime.now(timezone.utc)
    stale = []
    for issue in issues:
        labels = agentic.labels(issue)
        if not labels & active_labels:
            continue
        try:
            updated = datetime.fromisoformat(str(issue.get("updated_at") or "").replace("Z", "+00:00"))
        except ValueError:
            continue
        if updated.tzinfo is None:
            updated = updated.replace(tzinfo=timezone.utc)
        if (now - updated).total_seconds() < stale_minutes * 60:
            continue
        number = int(issue.get("number") or 0)
        if number > 0:
            stale.append((number, labels & active_labels))
    if not stale or _live_agentic_worker_exists(repository, token):
        return []
    reclaimed = []
    for number, labels in stale:
        for label in sorted(labels):
            agentic.remove_label(repository, token, number, label)
        reclaimed.append(number)
    return reclaimed


def _active_issue_numbers_from_issues(issues: list[dict]) -> list[int]:
    active: list[int] = []
    active_labels = (set(agentic.ACTIVE_LABELS) - {"genesis-deepseek-handoff-pending"}) | {
        "genesis-claimed",
        "genesis-deepseek-working",
    }
    for issue in issues:
        if agentic.labels(issue) & active_labels:
            number = int(issue.get("number") or 0)
            if number > 0:
                active.append(number)
    return active


def _active_issue_numbers(repository: str, token: str) -> list[int]:
    active: list[int] = []
    # A handoff-pending label is only a dispatch reservation, not proof that a
    # worker is actually running. Counting it as active can permanently consume
    # the single sequential slot after a failed/stale provider handoff and stop
    # Recovery from reclaiming the focused issue.
    active_labels = (set(agentic.ACTIVE_LABELS) - {"genesis-deepseek-handoff-pending"}) | {
        "genesis-claimed",
        "genesis-deepseek-working",
    }
    for issue in policy._all_open_issues_fifo(repository, token):
        if agentic.labels(issue) & active_labels:
            number = int(issue.get("number") or 0)
            if number > 0:
                active.append(number)
    return active


def main() -> int:
    repository = os.environ.get("GITHUB_REPOSITORY", "").strip()
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if not repository or not token:
        raise RuntimeError("GITHUB_REPOSITORY and GITHUB_TOKEN are required")

    skipped_this_pass: set[int] = set()
    comments_cache: dict[int, list[dict]] = {}

    def cached_comments(repo: str, gh_token: str, issue_number: int) -> list[dict]:
        number = int(issue_number)
        if number not in comments_cache:
            comments_cache[number] = policy._all_issue_comments(repo, gh_token, number)
        return comments_cache[number]

    agentic.issue_comments = cached_comments
    agentic.next_strategy = policy._least_recently_used_strategy

    try:
        all_open = policy._all_open_issues_fifo(repository, token)
    except RuntimeError as exc:
        message = str(exc)
        if "rate limit exceeded" in message.lower() or "http 403" in message.lower():
            print(json.dumps({
                "status": "deferred_rate_limit",
                "reason": "github_api_quota_unavailable",
                "detail": message[:500],
            }, sort_keys=True))
            return 0
        raise
    reclaimed_orphans = _reclaim_orphaned_reservations(repository, token, all_open)
    if reclaimed_orphans:
        all_open = policy._all_open_issues_fifo(repository, token)
    restored = policy._restore_agentic_visibility(repository, token, all_open)
    terminalized = policy._terminalize_non_actionable_issues(repository, token, all_open)
    if terminalized:
        all_open = policy._all_open_issues_fifo(repository, token)
    released = agentic.release_ready_capability_dependencies(repository, token)

    # Routing/decomposition is bounded per controller pass. One step per
    # configured worker slot is enough to prepare candidates without turning
    # every wake-up into an unbounded repository-wide maintenance scan.
    decomposition_steps: list[dict] = []
    seen_decomposition_actions: set[tuple[str, int, str]] = set()
    for _ in range(MAX_PARALLEL):
        step = _decompose_kernel_priority_issue(repository, token, all_open)
        if step is None:
            decomposition_order = _kernel_decomposition_order(all_open)
            step = policy._decompose_oldest_issue(repository, token, decomposition_order)
        key = (
            str(step.get("status") or ""),
            int(step.get("issue_number") or 0),
            str(step.get("target") or step.get("previous_target") or ""),
        )
        if key in seen_decomposition_actions:
            break
        seen_decomposition_actions.add(key)
        decomposition_steps.append(step)
        if step.get("status") not in {"decomposed", "retargeted", "target_revoked", "routing_released"}:
            break
        all_open = policy._all_open_issues_fifo(repository, token)
    decomposition = decomposition_steps[-1] if decomposition_steps else {"status": "idle"}

    # Freeze one bounded routing snapshot for this controller pass. Newly
    # dispatched issues are excluded locally through skipped_this_pass; a later
    # heartbeat gets a fresh repository snapshot.
    routing_snapshot = list(all_open)

    def routable_without_noops(repo: str, gh_token: str) -> list[dict]:
        # Exclude bounded no-op candidates *before* lane capacity is applied.
        # With one production slot, filtering after the lane selector allowed an
        # older no-op issue to consume the sole candidate position and made the
        # controller incorrectly report an empty queue.
        return _lane_routable_issues(
            repo,
            gh_token,
            all_open=routing_snapshot,
            comments_cache=comments_cache,
            excluded_issue_numbers=skipped_this_pass,
        )

    agentic.open_agentic_issues = routable_without_noops

    active_before = _active_issue_numbers_from_issues(routing_snapshot)
    free_slots = max(0, MAX_PARALLEL - len(active_before))
    dispatched: list[dict] = []

    noops: list[dict] = []
    attempts = 0
    max_attempts = max(
        MAX_PARALLEL,
        len(
            _parallel_routable_issues(
                repository,
                token,
                all_open=routing_snapshot,
                comments_cache=comments_cache,
            )
        ),
    )

    while len(dispatched) < free_slots and attempts < max_attempts:
        attempts += 1
        result = agentic.reserve_and_dispatch(repository, token)
        if not isinstance(result, dict):
            break
        if result.get("status") == "dispatched":
            dispatched.append(result)
            issue_number = int(result.get("issue_number") or 0)
            if issue_number > 0:
                skipped_this_pass.add(issue_number)
            continue

        issue_number = int(result.get("issue_number") or 0)
        noops.append({
            "issue_number": issue_number or None,
            "status": result.get("status"),
            "reason": result.get("reason"),
        })

        # A candidate can legitimately produce a bounded no-op (for example a
        # capability dependency is already ready). That must not starve other
        # independent lanes. Exclude only that candidate for this controller
        # pass, then continue scanning the ranked backlog.
        if issue_number > 0 and issue_number not in skipped_this_pass:
            skipped_this_pass.add(issue_number)
            continue

        # An idle/no-candidate result has nothing concrete to skip, so the
        # current admission pass is exhausted.
        break

    result = {
        "status": "parallel_dispatch_complete",
        "max_parallel": MAX_PARALLEL,
        "development_slots": DEVELOPMENT_SLOTS,
        "recovery_slots": RECOVERY_SLOTS,
        "active_before": active_before,
        "dispatched": [row.get("issue_number") for row in dispatched],
        "skipped_noop_candidates": sorted(skipped_this_pass),
        "noop_results": noops,
        "dispatch_attempts": attempts,
        "active_after": sorted(set(active_before + [int(row.get("issue_number") or 0) for row in dispatched if int(row.get("issue_number") or 0) > 0])),
        "legacy_dependencies_released": released,
        "capability_escalation": "enabled",
        "agentic_visibility_restored": restored,
        "orphaned_reservations_reclaimed": reclaimed_orphans,
        "terminalized_non_actionable": terminalized,
        "decomposition": decomposition,
        "decomposition_steps": decomposition_steps,
        "strategies": list(agentic.STRATEGIES),
    }
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
