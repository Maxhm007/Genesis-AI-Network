from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


AUTONOMOUS_LABEL = "genesis-autonomous"
TASK_LABEL = "genesis-task"
IN_PROGRESS_LABEL = "genesis-repair-in-progress"
VALIDATING_LABEL = "genesis-validating"
BLOCKED_LABEL = "genesis-blocked"
SOLVED_LABEL = "genesis-solved"
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


def _sort_key(row: dict) -> int:
    """Order eligible Issues strictly oldest-first by GitHub Issue number."""
    # GitHub assigns repository Issue/PR numbers monotonically. Among Issues,
    # a lower Issue number was created earlier, so it is a stable FIFO key that
    # cannot be changed by comments, labels, retries, or other updates.
    return _number(row)


def select_issue_repair_batch(
    issues: Iterable[dict],
    *,
    max_parallel: int = DEFAULT_MAX_PARALLEL,
    explicit_issue_number: int | None = None,
) -> IssueRepairBatch:
    """Select a bounded oldest-first GitHub Issue repair batch.

    GitHub Issues are the authoritative task source. Existing autonomous issues,
    canonical ``genesis-task`` issues, and explicit Genesis task-title records are
    eligible without requiring a second queue-admission mutation.

    Active repairs include both the model/repair stage and independent validation.
    This means a candidate under ``genesis-validating`` still consumes a worker slot,
    preventing validation-heavy work from causing unbounded admission.

    Selection is deterministic FIFO across the generic code-repair lane: the lowest
    eligible GitHub Issue number wins. ``updatedAt`` and title priority do not affect
    queue position, so comments, retries, labels, or newer repair/security Issues
    cannot jump ahead of older eligible work. Dedicated non-code research/self-
    improvement task families remain in their specialist Issue-backed lanes.

    An explicit dispatch is only admitted when it names the oldest currently
    eligible Issue. This keeps manual/event-driven wakeups from bypassing FIFO.
    """

    rows = [row for row in issues if isinstance(row, dict) and _is_open(row)]
    active_numbers = sorted({_number(row) for row in rows if _is_active(row) and _number(row)})
    bounded_max = max(1, min(int(max_parallel), DEFAULT_MAX_PARALLEL))
    slots = max(0, bounded_max - len(active_numbers))

    if slots == 0:
        return IssueRepairBatch((), tuple(active_numbers), 0)

    eligible = sorted((row for row in rows if _is_eligible(row)), key=_sort_key)

    if explicit_issue_number is not None:
        explicit = int(explicit_issue_number)
        if eligible and _number(eligible[0]) == explicit:
            return IssueRepairBatch((explicit,), tuple(active_numbers), slots)
        return IssueRepairBatch((), tuple(active_numbers), slots)

    selected = tuple(_number(row) for row in eligible[:slots])
    return IssueRepairBatch(selected, tuple(active_numbers), slots)
