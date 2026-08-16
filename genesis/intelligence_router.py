from __future__ import annotations

from dataclasses import dataclass

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

    Genesis is intentionally provider-agnostic. Routing optimizes capability per
    resource rather than always selecting the strongest or largest model.
    Profiles are conservative defaults and should later be replaced by measured
    benchmark telemetry for each provider.
    """

    def __init__(self, registry: ProviderRegistry) -> None:
        self.registry = registry

    @staticmethod
    def profile(provider: IntelligenceProvider) -> ProviderProfile:
        name = getattr(provider, "name", "unknown")
        lowered = name.lower()
        if name == "genesis-bootstrap":
            return ProviderProfile(name, 0.05, 0.35, ("planning", "review", "routing"))
        if "qwen3-0.6b" in lowered:
            return ProviderProfile(name, 1.0, 0.72, ("reasoning", "coding", "research", "planning"))
        return ProviderProfile(name, 2.0, 0.75, ("reasoning", "coding", "research", "planning", "review"))

    def select(self, task_type: str, *, complexity: float = 0.5, require_non_bootstrap: bool = False) -> RouteDecision:
        task_type = task_type.strip().lower() or "reasoning"
        complexity = max(0.0, min(1.0, float(complexity)))
        candidates: list[tuple[float, IntelligenceProvider, ProviderProfile]] = []
        for provider in self.registry.available_providers():
            profile = self.profile(provider)
            if require_non_bootstrap and profile.name == "genesis-bootstrap":
                continue
            if task_type not in profile.capabilities and "reasoning" not in profile.capabilities:
                continue
            required_reliability = 0.3 + (0.45 * complexity)
            if profile.reliability < required_reliability:
                continue
            # Lower is better. Reliability reduces effective resource cost.
            score = profile.resource_cost / max(profile.reliability, 0.05)
            candidates.append((score, provider, profile))
        if not candidates:
            raise RuntimeError(f"no suitable intelligence provider for {task_type}")
        candidates.sort(key=lambda item: (item[0], item[2].name))
        _, provider, profile = candidates[0]
        return RouteDecision(
            provider=provider,
            profile=profile,
            reason=f"lowest measured/default resource cost meeting reliability threshold for {task_type}",
        )
