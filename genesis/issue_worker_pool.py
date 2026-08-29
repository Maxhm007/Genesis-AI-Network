from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


AUTONOMOUS_LABEL = "genesis-autonomous"
TASK_LABEL = "genesis-task"
IN_PROGRESS_LABEL = "genesis-repair-in-progress"
VALIDATING_LABEL = "genesis-validating"
BLOCKED_LABEL = "genesis-blocked"
SOLVED_LABEL = "genesis-solved"
ACTION_FAILURE_LABEL = "genesis-action-failure"
PERSISTENT_LABEL = "genesis-persistent"
CONTROL_LABEL = "genesis-control"
DUPLICATE_LABEL = "duplicate"
DEFAULT_MAX_PARALLEL = 5

AUTHORIZED_TITLE_PREFIXES = (
    "[Genesis Task]",
    "[Genesis Repair]",
    "[Genesis Self Improvement]",
    "Genesis challenge:",
)

# These Issue-backed task families have dedicated non-code execution/review lanes.
# The generic GitHub autorepair worker must not force them through a coding model.
_NON_CODE_TASK_PREFIXES = (
    "[genesis self improvement]",
    "[genesis task] competitive ai improvement",
    "[genesis task] competitive reference refresh",
    "[genesis task] immortality research",
)

_HIGH_PRIORITY_TASK_PREFIXES = (
    "[genesis task] self repair",
    "[genesis task] security repair",
    "[genesis task] action repair",
    "[genesis task] workflow repair",
    "[genesis task] issue repair",
)
_LOW_PRIORITY_TASK_MARKERS = (
    "capability",
    "benchmark",
    "application development",
    "research",
    "model evaluation",
    "self improvement",
    "self upgrade",
)


@dataclass(frozen=True)
class IssueRepairBatch:
    selected_issue_numbers: tuple[int, ...]
    active_issue_numbers: tuple[int, ...]
    available_slots: int

    def as_dict(self) -> dict:
        return {
            "selected_issue_numbers": list(self.selected_issue_numbers),
            "active_issue_numbers": list(self.active_issue_numbers),
            "available_slots": self.available_slots,
        }


def _number(row: dict) -> int:
    try:
        return int(row.get("number") or 0)
    except (TypeError, ValueError):
        return 0


def _labels(row: dict) -> set[str]:
    values: set[str] = set()
    for label in row.get("labels") or []:
        if isinstance(label, dict):
            name = str(label.get("name") or "").strip()
        else:
            name = str(label or "").strip()
        if name:
            values.add(name)
    return values


def _is_open(row: dict) -> bool:
    state = str(row.get("state") or "OPEN").strip().upper()
    return state == "OPEN"


def _is_active(row: dict) -> bool:
    labels = _labels(row)
    return IN_PROGRESS_LABEL in labels or VALIDATING_LABEL in labels


def _has_authority(row: dict, labels: set[str]) -> bool:
    if AUTONOMOUS_LABEL in labels or TASK_LABEL in labels:
        return True
    title = str(row.get("title") or "").strip()
    return any(title.startswith(prefix) for prefix in AUTHORIZED_TITLE_PREFIXES)


def _uses_generic_code_repair(row: dict) -> bool:
    """Return False for Issue types that already have a specialist execution lane."""
    title = str(row.get("title") or "").strip().lower()
    return not title.startswith(_NON_CODE_TASK_PREFIXES)


def _is_eligible(row: dict) -> bool:
    if not _is_open(row) or not _number(row):
        return False
    labels = _labels(row)
    if not _has_authority(row, labels):
        return False
    if not _uses_generic_code_repair(row):
        return False
    if labels & {
        IN_PROGRESS_LABEL,
        VALIDATING_LABEL,
        BLOCKED_LABEL,
        SOLVED_LABEL,
        PERSISTENT_LABEL,
        CONTROL_LABEL,
        DUPLICATE_LABEL,
    }:
        return False
    if str(row.get("title") or "").strip().startswith("Genesis Control:"):
        return False
    return True


def _drain_priority(row: dict) -> int:
    """Prefer backlog-closing repair work without starving older work in a class."""
    title = str(row.get("title") or "").strip().lower()
    labels = _labels(row)
    if (
        title.startswith("[genesis repair]")
        or title.startswith("genesis control:")
        or title.startswith(_HIGH_PRIORITY_TASK_PREFIXES)
        or ACTION_FAILURE_LABEL in labels
    ):
        return 0
    if title.startswith("genesis challenge:"):
        return 1
    if title.startswith("[genesis self improvement]"):
        return 3
    if title.startswith("[genesis task]") and any(marker in title for marker in _LOW_PRIORITY_TASK_MARKERS):
        return 3
    return 2


def _sort_key(row: dict) -> tuple[int, str, int]:
    return (
        _drain_priority(row),
        str(row.get("updatedAt") or row.get("updated_at") or ""),
        _number(row),
    )


def select_issue_repair_batch(
    issues: Iterable[dict],
    *,
    max_parallel: int = DEFAULT_MAX_PARALLEL,
    explicit_issue_number: int | None = None,
) -> IssueRepairBatch:
    """Select a bounded, backlog-draining issue-repair batch.

    GitHub Issues are the authoritative task source. Existing autonomous issues,
    canonical ``genesis-task`` issues, and explicit Genesis task-title records are
    eligible without requiring a second queue-admission mutation.

    Active repairs include both the model/repair stage and independent validation.
    This means a candidate under ``genesis-validating`` still consumes a worker slot,
    preventing validation-heavy work from causing unbounded admission.

    Selection is deterministic and drain-aware: repair/security/control work wins
    before challenge/general work, while research/self-improvement/capability work
    is drained last. Dedicated non-code research/self-improvement task families are
    excluded from this generic coding pool and remain executable through their
    specialist Issue-backed workers. Within each class, least-recently-updated wins,
    then issue number, so fairness is preserved. An explicit manual issue is admitted
    only if it is currently eligible and capacity exists.
    """

    rows = [row for row in issues if isinstance(row, dict) and _is_open(row)]
    active_numbers = sorted({_number(row) for row in rows if _is_active(row) and _number(row)})
    bounded_max = max(1, min(int(max_parallel), DEFAULT_MAX_PARALLEL))
    slots = max(0, bounded_max - len(active_numbers))

    if slots == 0:
        return IssueRepairBatch((), tuple(active_numbers), 0)

    if explicit_issue_number is not None:
        explicit = int(explicit_issue_number)
        for row in rows:
            if _number(row) == explicit and _is_eligible(row):
                return IssueRepairBatch((explicit,), tuple(active_numbers), slots)
        return IssueRepairBatch((), tuple(active_numbers), slots)

    eligible = sorted((row for row in rows if _is_eligible(row)), key=_sort_key)
    selected = tuple(_number(row) for row in eligible[:slots])
    return IssueRepairBatch(selected, tuple(active_numbers), slots)
