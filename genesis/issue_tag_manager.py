from __future__ import annotations

from dataclasses import dataclass

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

PROTECTED_MANUAL_LABELS = {
    "security",
    "critical",
    "owner-priority",
    "owner_priority",
    "production-down",
    "bug",
    "enhancement",
    "documentation",
    "duplicate",
    "invalid",
    "wontfix",
}

# Canonical Genesis-owned label metadata. Genesis may create/update these labels.
GENESIS_LABELS: dict[str, tuple[str, str]] = {
    "genesis-autonomous": ("1f883d", "Authorized for Genesis autonomous repair"),
    "genesis-claimed": ("1f6feb", "Claimed by the Genesis issue lifecycle"),
    "genesis-working": ("fbca04", "Genesis is actively working this issue"),
    "genesis-repair-in-progress": ("b60205", "Reserved for one bounded Genesis repair worker"),
    "genesis-validating": ("8250df", "Genesis is independently validating a candidate"),
    "genesis-verifying": ("8250df", "Genesis is verifying completion evidence"),
    "genesis-solver-exhausted": ("6e7781", "Bounded solver exhausted; issue requires recovery"),
    "genesis-blocked": ("d73a4a", "Genesis cannot safely advance this issue yet"),
    "genesis-verified": ("0e8a16", "Genesis independently verified completion"),
    "genesis-superseded": ("6e7781", "Current authority marks this issue duplicate, superseded, or orphaned"),
    "agentic-lab": ("8250df", "Agentic Lab recovery owns this issue"),
    "genesis-action-failure": ("d1242f", "A GitHub Actions workflow failed and requires recovery"),
    "genesis-deepseek-agentic": ("5319e7", "DeepSeek agentic repair lane"),
    "genesis-qwen3-agentic": ("5319e7", "Qwen3 agentic repair lane"),
    "genesis-integration-route": ("5319e7", "Integration-sensitive repair route"),
    "genesis-specialist": ("5319e7", "Specialist repair lane"),
    "gene-peer-sync": ("0e8a16", "Issue synchronized from a Genesis peer Gene"),
}

# Obsolete Genesis-owned labels are migrated to the canonical replacement.
LABEL_ALIASES: dict[str, str] = {
    "genesis-in-progress": "genesis-working",
    "genesis-repairing": "genesis-repair-in-progress",
    "genesis-validation": "genesis-validating",
    "genesis-action-error": "genesis-action-failure",
}

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

def is_genesis_owned(name: str) -> bool:
    name = str(name or "").strip()
    if not name or name in PROTECTED_MANUAL_LABELS:
        return False
    return name.startswith("genesis-") or name in {"agentic-lab", "gene-peer-sync"}

def canonicalize_issue_tags(issue: dict) -> TagPlan:
    """Return Genesis-owned label corrections without changing issue semantics."""
    labels = _names(issue)
    add: set[str] = set()
    remove: set[str] = set()

    for old, new in LABEL_ALIASES.items():
        if old in labels:
            remove.add(old)
            add.add(new)

    effective = (labels - remove) | add

    if effective & TERMINAL_FLAGS:
        remove.update(label for label in LIFECYCLE_STATES if label in effective)
        remove.update({"genesis-autonomous", "genesis-deferred"})
        return TagPlan(tuple(sorted(add)), tuple(sorted(remove)), "terminal_state_authority")

    active = [label for label in LIFECYCLE_STATES if label in effective]
    if len(active) > 1:
        winner = active[-1]
        remove.update(label for label in active if label != winner)
        return TagPlan(tuple(sorted(add)), tuple(sorted(remove)), f"exclusive_lifecycle:{winner}")

    if "genesis-solver-exhausted" in effective and "agentic-lab" not in effective:
        add.add("agentic-lab")

    if "genesis-repair-in-progress" in effective and "genesis-autonomous" not in effective:
        add.add("genesis-autonomous")

    reason = "already_canonical" if not add and not remove else "genesis_tag_authority"
    return TagPlan(tuple(sorted(add)), tuple(sorted(remove)), reason)

def desired_label_definition(name: str) -> tuple[str, str] | None:
    return GENESIS_LABELS.get(name)

def retired_genesis_labels(existing_names: set[str], used_names: set[str]) -> tuple[str, ...]:
    """Return obsolete Genesis-owned labels safe to delete from repository metadata.

    A label is retired only when Genesis owns it, it is not canonical, and no
    current issue uses it. Manual/protected labels are never candidates.
    """
    canonical = set(GENESIS_LABELS)
    aliases = set(LABEL_ALIASES)
    retired = {
        name for name in existing_names
        if is_genesis_owned(name)
        and name not in canonical
        and name not in aliases
        and name not in used_names
    }
    return tuple(sorted(retired))
