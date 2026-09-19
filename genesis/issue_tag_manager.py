from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

LIFECYCLE_STATES = (
    "genesis-claimed",
    "genesis-working",
    "genesis-repair-in-progress",
    "genesis-validating",
    "genesis-verifying",
    "genesis-solver-exhausted",
    "genesis-blocked",
)

TERMINAL_FLAGS = {
    "genesis-verified",
    "genesis-superseded",
    "genesis-closed-sealed-completed",
    "genesis-closed-sealed-not-planned",
}

CLASSIFICATION_PREFIXES = (
    "genesis-action-",
    "genesis-deepseek-",
    "genesis-qwen3-",
    "genesis-integration-",
    "genesis-specialist",
    "gene-peer-sync",
    "agentic-lab",
)

@dataclass(frozen=True)
class TagPlan:
    add: tuple[str, ...] = ()
    remove: tuple[str, ...] = ()
    reason: str = ""

def _names(issue: dict) -> set[str]:
    out: set[str] = set()
    for row in issue.get("labels") or []:
        if isinstance(row, dict):
            name = str(row.get("name") or "").strip()
        else:
            name = str(row or "").strip()
        if name:
            out.add(name)
    return out

def canonicalize_issue_tags(issue: dict) -> TagPlan:
    """Return Genesis-owned label corrections without changing issue semantics.

    Classification labels may coexist. Lifecycle execution labels are exclusive:
    the most advanced current state wins. Terminal verified/superseded state
    clears active execution state. This makes Genesis, not individual workers,
    the final authority over contradictory tag combinations.
    """
    labels = _names(issue)
    remove: set[str] = set()

    if labels & TERMINAL_FLAGS:
        remove.update(label for label in LIFECYCLE_STATES if label in labels)
        remove.update({"genesis-autonomous", "genesis-deferred"})
        return TagPlan(remove=tuple(sorted(remove)), reason="terminal_state_authority")

    active = [label for label in LIFECYCLE_STATES if label in labels]
    if len(active) > 1:
        # Ordered from early -> late; keep the furthest progressed state.
        winner = active[-1]
        remove.update(label for label in active if label != winner)
        return TagPlan(remove=tuple(sorted(remove)), reason=f"exclusive_lifecycle:{winner}")

    if "genesis-solver-exhausted" in labels and "agentic-lab" not in labels:
        return TagPlan(add=("agentic-lab",), reason="exhausted_requires_agentic_owner")

    if "genesis-repair-in-progress" in labels and "genesis-autonomous" not in labels:
        return TagPlan(add=("genesis-autonomous",), reason="repair_requires_autonomous_authority")

    return TagPlan(reason="already_canonical")

def classification_labels(issue: dict) -> tuple[str, ...]:
    labels = _names(issue)
    return tuple(sorted(
        label for label in labels
        if any(label.startswith(prefix) for prefix in CLASSIFICATION_PREFIXES)
    ))
