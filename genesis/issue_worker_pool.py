from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


AUTONOMOUS_LABEL = "genesis-autonomous"
IN_PROGRESS_LABEL = "genesis-repair-in-progress"
VALIDATING_LABEL = "genesis-validating"
BLOCKED_LABEL = "genesis-blocked"
SOLVED_LABEL = "genesis-solved"
DEFAULT_MAX_PARALLEL = 5


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


def _is_eligible(row: dict) -> bool:
    if not _is_open(row) or not _number(row):
        return False
    labels = _labels(row)
    if AUTONOMOUS_LABEL not in labels:
        return False
    if labels & {IN_PROGRESS_LABEL, VALIDATING_LABEL, BLOCKED_LABEL, SOLVED_LABEL}:
        return False
    return True


def _sort_key(row: dict) -> tuple[str, int]:
    return (str(row.get("updatedAt") or row.get("updated_at") or ""), _number(row))


def select_issue_repair_batch(
    issues: Iterable[dict],
    *,
    max_parallel: int = DEFAULT_MAX_PARALLEL,
    explicit_issue_number: int | None = None,
) -> IssueRepairBatch:
    """Select a bounded, fair issue-repair batch from a GitHub issue snapshot.

    Active repairs include both the model/repair stage and independent validation.
    This means a candidate under ``genesis-validating`` still consumes a worker slot,
    preventing validation-heavy work from causing unbounded admission.

    Selection is deterministic: least-recently-updated eligible issues win, then
    issue number. An explicit manual issue is admitted only if it is currently
    eligible and capacity exists.
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