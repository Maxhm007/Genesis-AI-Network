from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .capability_integration import ProviderTelemetryStore
from .providers import IntelligenceProvider, ProviderRegistry


@dataclass(frozen=True)
class ProviderProfile:
    name: str
    resource_cost: float
    reliability: float
    capabilities: tuple[str, ...]


@dataclass(frozen=True)
class RouteDecision:
    provider: IntelligenceProvider
    profile: ProviderProfile
    reason: str


class IntelligenceRouter:
    """Choose the lowest-resource available provider likely to satisfy a task.

    Conservative defaults bootstrap routing. Once at least three evidence-backed
    provider observations exist, measured reliability/resource telemetry may
    replace the default cost/reliability values. Measured capability names are
    added to, not allowed to erase, the provider's declared/default abilities.
    """

    def __init__(self, registry: ProviderRegistry, telemetry_path: Path | None = None) -> None:
        self.registry = registry
        self.telemetry = ProviderTelemetryStore(telemetry_path) if telemetry_path is not None else None

    @staticmethod
    def profile(provider: IntelligenceProvider) -> ProviderProfile:
        name = getattr(provider, "name", "unknown")
        lowered = name.lower()
        if name == "genesis-bootstrap":
            return ProviderProfile(name, 0.05, 0.35, ("planning", "review", "routing"))
        if "claude" in lowered or "anthropic" in lowered:
            return ProviderProfile(name, 1.1, 0.96, ("reasoning", "coding", "research", "planning", "review"))
        if "qwen3-0.6b" in lowered:
            return ProviderProfile(name, 1.0, 0.72, ("reasoning", "coding", "research", "planning"))
        return ProviderProfile(name, 2.0, 0.75, ("reasoning", "coding", "research", "planning", "review"))

    def _effective_profile(self, provider: IntelligenceProvider) -> tuple[ProviderProfile, str]:
        default = self.profile(provider)
        if self.telemetry is None:
            return default, "default"
        measured = self.telemetry.measured_profile(default.name)
        if measured is None:
            return default, "default"
        capabilities = tuple(sorted(set(default.capabilities) | set(measured.capabilities)))
        return (
            ProviderProfile(
                name=default.name,
                resource_cost=measured.resource_cost,
                reliability=measured.reliability,
                capabilities=capabilities,
            ),
            f"measured:{measured.samples}",
        )

    def select(self, task_type: str, *, complexity: float = 0.5, require_non_bootstrap: bool = False) -> RouteDecision:
        task_type = task_type.strip().lower() or "reasoning"
        complexity = max(0.0, min(1.0, float(complexity)))
        candidates: list[tuple[float, IntelligenceProvider, ProviderProfile, str]] = []
        for provider in self.registry.available_providers():
            profile, source = self._effective_profile(provider)
            if require_non_bootstrap and profile.name == "genesis-bootstrap":
                continue
            if task_type not in profile.capabilities and "reasoning" not in profile.capabilities:
                continue
            required_reliability = 0.3 + (0.45 * complexity)
            if profile.reliability < required_reliability:
                continue
            score = profile.resource_cost / max(profile.reliability, 0.05)
            candidates.append((score, provider, profile, source))
        if not candidates:
            raise RuntimeError(f"no suitable intelligence provider for {task_type}")
        candidates.sort(key=lambda item: (item[0], item[2].name))
        _, provider, profile, source = candidates[0]
        return RouteDecision(
            provider=provider,
            profile=profile,
            reason=f"lowest resource cost meeting reliability threshold for {task_type}; profile={source}",
        )
