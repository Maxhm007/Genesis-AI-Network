from __future__ import annotations

from dataclasses import dataclass


CORE_LOGICAL_ID = "gene-node-1"
CORE_DISPLAY_NAME = "Gene 0"
RESERVED_DISPLAY_NAME = "Gene 001"
COMMON_NAME = "Gene"


@dataclass(frozen=True)
class GeneDisplayIdentity:
    logical_id: str
    common_name: str
    display_name: str
    serial: int
    reserved: bool = False


def identity_for_logical_id(logical_id: str) -> GeneDisplayIdentity:
    """Return Gene's canonical human-facing identity for an internal logical ID.

    Legacy/internal IDs remain stable for compatibility. Human-facing identities are:
    - gene-node-1 -> Gene 0
    - Gene 001 is reserved and intentionally has no logical node yet
    - gene-node-N for N >= 2 -> Gene NNN (zero padded to three digits)
    """
    if logical_id == CORE_LOGICAL_ID:
        return GeneDisplayIdentity(logical_id, COMMON_NAME, CORE_DISPLAY_NAME, 0)

    prefix = "gene-node-"
    if not logical_id.startswith(prefix):
        raise ValueError(f"unsupported Gene logical id: {logical_id}")
    suffix = logical_id[len(prefix):]
    if not suffix.isdigit():
        raise ValueError(f"unsupported Gene logical id: {logical_id}")
    serial = int(suffix)
    if serial < 2:
        raise ValueError("Gene 001 is reserved and cannot be assigned automatically")
    return GeneDisplayIdentity(logical_id, COMMON_NAME, f"Gene {serial:03d}", serial)


def logical_id_for_display_name(display_name: str) -> str | None:
    normalized = display_name.strip()
    if normalized.lower() == "gene":
        return None
    if normalized == CORE_DISPLAY_NAME:
        return CORE_LOGICAL_ID
    if normalized == RESERVED_DISPLAY_NAME:
        return None
    if normalized.startswith("Gene ") and normalized[5:].isdigit():
        serial = int(normalized[5:])
        if serial >= 2:
            return f"gene-node-{serial}"
    raise ValueError(f"unsupported Gene display name: {display_name}")


def public_naming_scheme() -> dict[str, object]:
    return {
        "common_name": COMMON_NAME,
        "core": {"logical_id": CORE_LOGICAL_ID, "display_name": CORE_DISPLAY_NAME, "serial": 0},
        "reserved": {"display_name": RESERVED_DISPLAY_NAME, "serial": 1, "status": "reserved_for_owner_definition"},
        "sequence_rule": "gene-node-N where N>=2 is displayed as Gene NNN",
        "examples": {
            "gene-node-2": "Gene 002",
            "gene-node-3": "Gene 003",
            "gene-node-4": "Gene 004",
            "gene-node-5": "Gene 005",
        },
    }
