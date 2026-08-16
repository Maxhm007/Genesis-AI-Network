from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


PROVIDER_STATES = (
    "DISCOVERED",
    "QUARANTINED",
    "TESTED",
    "VALIDATED",
    "TRUSTED",
    "ACTIVE",
)

_ALLOWED_TRANSITIONS = {
    "DISCOVERED": {"QUARANTINED"},
    "QUARANTINED": {"TESTED"},
    "TESTED": {"VALIDATED", "QUARANTINED"},
    "VALIDATED": {"TRUSTED", "QUARANTINED"},
    "TRUSTED": {"ACTIVE", "QUARANTINED"},
    "ACTIVE": {"TRUSTED", "QUARANTINED"},
}


@dataclass
class ProviderCandidate:
    provider_id: str
    provider_type: str
    model_id: str | None
    state: str
    source: str
    license: str | None = None
    capabilities: list[str] = field(default_factory=list)
    evidence: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.state not in PROVIDER_STATES:
            raise ValueError(f"invalid provider state: {self.state}")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ProviderTrustRegistry:
    """Persistent trust-state registry for replaceable intelligence providers.

    Genesis identity never depends on a provider. New providers must progress
    through explicit trust states and can be demoted back to quarantine.
    """

    def __init__(self, path: Path) -> None:
        self.path = path
        self._providers: dict[str, ProviderCandidate] = {}
        if path.exists():
            self.load()

    def load(self) -> None:
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        items = payload.get("providers", [])
        if not isinstance(items, list):
            raise ValueError("provider registry must contain a providers list")
        self._providers = {}
        for item in items:
            candidate = ProviderCandidate(**item)
            self._providers[candidate.provider_id] = candidate

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": 1,
            "providers": [self._providers[key].to_dict() for key in sorted(self._providers)],
        }
        self.path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    def register(self, candidate: ProviderCandidate) -> None:
        if candidate.provider_id in self._providers:
            raise ValueError("provider already registered")
        self._providers[candidate.provider_id] = candidate

    def get(self, provider_id: str) -> ProviderCandidate | None:
        return self._providers.get(provider_id)

    def all(self) -> tuple[ProviderCandidate, ...]:
        return tuple(self._providers[key] for key in sorted(self._providers))

    def transition(self, provider_id: str, new_state: str, evidence: dict[str, Any] | None = None) -> ProviderCandidate:
        if new_state not in PROVIDER_STATES:
            raise ValueError(f"invalid provider state: {new_state}")
        candidate = self._providers[provider_id]
        if new_state not in _ALLOWED_TRANSITIONS[candidate.state]:
            raise ValueError(f"invalid provider transition: {candidate.state} -> {new_state}")
        if new_state in {"TESTED", "VALIDATED", "TRUSTED", "ACTIVE"} and not evidence:
            raise ValueError("evidence is required for trust advancement")
        candidate.state = new_state
        if evidence:
            candidate.evidence.append(dict(evidence))
        return candidate

    def active(self) -> tuple[ProviderCandidate, ...]:
        return tuple(item for item in self.all() if item.state == "ACTIVE")
