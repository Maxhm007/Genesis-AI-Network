from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class ModuleManifest:
    module_id: str
    name: str
    version: str
    purpose: str
    capabilities: list[str]
    permissions: list[str]
    dependencies: list[str] = field(default_factory=list)
    status: str = "active"
    dynamic: bool = False
    mutable: bool = True
    protected: bool = False
    implementation: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ModuleProposal:
    proposal_id: str
    action: str  # add | modify | split | merge | replace | retire | reactivate
    target_module_id: str | None
    title: str
    rationale: str
    requested_by: str
    capability: str | None = None
    current_score: float | None = None
    target_score: float | None = None
    candidate_manifest: dict[str, Any] = field(default_factory=dict)
    status: str = "candidate"
    created_at: str = field(default_factory=utc_now)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
