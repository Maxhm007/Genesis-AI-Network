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
    """Choose the preferred available cognitive provider for a task.

    Trained providers may declare a bounded capability set plus resource and
    reliability metadata. The router respects those declarations instead of
    silently granting every trained provider coding/reasoning authority. The
    deterministic bootstrap provider remains a last-resort control-plane
    fallback and is never preferred over an eligible trained model.

    Conservative defaults bootstrap routing. Once at least three evidence-backed
    provider observations exist, measured reliability/resource telemetry may
    replace the default cost/reliability values. Measured capability names are
    added to, not allowed to erase, the provider's declared/default abilities.
    """

    def __init__(self, registry: ProviderRegistry, telemetry_path: Path | None = None) -> None:
        self.registry = registry
        self.telemetry = ProviderTelemetryStore(telemetry_path) if telemetry_path is not None else None

    @staticmethod
    def _bounded_float(value: object, default: float, *, minimum: float, maximum: float) -> float:
        try:
            return max(minimum, min(float(value), maximum))
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _declared_capabilities(provider: IntelligenceProvider) -> tuple[str, ...] | None:
        raw = getattr(provider, "capabilities", None)
        if raw is None:
            return None
        if not isinstance(raw, (tuple, list, set, frozenset)):
            return ()
        allowed = {"reasoning", "coding", "research", "planning", "review", "routing"}
        return tuple(sorted({str(item).strip().lower() for item in raw if str(item).strip().lower() in allowed}))

    @classmethod
    def profile(cls, provider: IntelligenceProvider) -> ProviderProfile:
        name = getattr(provider, "name", "unknown")
        lowered = name.lower()
        declared = cls._declared_capabilities(provider)
        if name == "genesis-bootstrap":
            return ProviderProfile(name, 0.05, 0.35, declared or ("planning", "review", "routing"))
        default_capabilities = ("reasoning", "coding", "research", "planning", "review")
        capabilities = default_capabilities if declared is None else declared
        if "qwen" in lowered:
            return ProviderProfile(
                name,
                cls._bounded_float(getattr(provider, "resource_cost", 1.0), 1.0, minimum=0.05, maximum=100.0),
                cls._bounded_float(getattr(provider, "reliability", 0.72), 0.72, minimum=0.0, maximum=1.0),
                capabilities,
            )
        return ProviderProfile(
            name,
            cls._bounded_float(getattr(provider, "resource_cost", 2.0), 2.0, minimum=0.05, maximum=100.0),
            cls._bounded_float(getattr(provider, "reliability", 0.75), 0.75, minimum=0.0, maximum=1.0),
            capabilities,
        )

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
        trained: list[tuple[int, float, IntelligenceProvider, ProviderProfile, str]] = []
        bootstrap: list[tuple[float, IntelligenceProvider, ProviderProfile, str]] = []
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
            if profile.name == "genesis-bootstrap":
                bootstrap.append((score, provider, profile, source))
                continue
            qwen_priority = 0 if "qwen" in profile.name.lower() else 1
            trained.append((qwen_priority, score, provider, profile, source))

        if trained:
            trained.sort(key=lambda item: (item[0], item[1], item[3].name))
            qwen_priority, _, provider, profile, source = trained[0]
            lineage = "qwen_cognitive_ancestor" if qwen_priority == 0 else "trained_provider_fallback"
            return RouteDecision(
                provider=provider,
                profile=profile,
                reason=f"{lineage} selected for {task_type}; profile={source}",
            )

        if bootstrap:
            bootstrap.sort(key=lambda item: (item[0], item[2].name))
            _, provider, profile, source = bootstrap[0]
            return RouteDecision(
                provider=provider,
                profile=profile,
                reason=f"deterministic bootstrap fallback for {task_type}; profile={source}",
            )

        raise RuntimeError(f"no suitable intelligence provider for {task_type}")
