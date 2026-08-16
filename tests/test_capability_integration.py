from pathlib import Path

from genesis.capability_integration import CapabilityGrowthCoordinator, ProviderTelemetryStore
from genesis.intelligence_router import IntelligenceRouter
from genesis.providers import ProviderRegistry


class FakeProvider:
    name = "measured-provider"

    def available(self) -> bool:
        return True

    def reason(self, prompt: str) -> str:
        return "ok"


def test_provider_telemetry_requires_three_samples_before_routing(tmp_path: Path):
    store = ProviderTelemetryStore(tmp_path / "provider.json")
    for index in range(2):
        store.record(
            provider="measured-provider",
            capability="coding",
            quality=0.9,
            success=True,
            resource_cost=0.4,
            evidence_count=1,
        )
        assert store.measured_profile("measured-provider") is None
    store.record(
        provider="measured-provider",
        capability="coding",
        quality=0.9,
        success=True,
        resource_cost=0.4,
        evidence_count=1,
    )
    profile = store.measured_profile("measured-provider")
    assert profile is not None
    assert profile.samples == 3
    assert profile.resource_cost == 0.4


def test_capability_growth_connects_evaluation_experiment_and_model_scout(tmp_path: Path):
    coordinator = CapabilityGrowthCoordinator(tmp_path)
    result = coordinator.observe_provider(
        provider="candidate-model",
        capability="coding",
        score=0.8,
        max_score=1.0,
        baseline_score=0.5,
        resource_cost=0.7,
        success=True,
        evidence_count=1,
        source="benchmark-suite",
        provenance="run-1",
    )
    assert result["evaluation"]["normalized"] == 0.8
    assert result["experiment"]["decision"] == "keep"
    assert result["evidence"]["status"] == "reviewed"
    assert result["model_candidate"]["state"] == "tested"
    assert result["recommended_model_transition"] == "validated"
    assert result["automatic_activation"] is False


def test_router_uses_measured_profile_only_when_ready(tmp_path: Path):
    telemetry = tmp_path / "provider.json"
    store = ProviderTelemetryStore(telemetry)
    for _ in range(3):
        store.record(
            provider="measured-provider",
            capability="coding",
            quality=1.0,
            success=True,
            resource_cost=0.2,
            evidence_count=1,
        )
    registry = ProviderRegistry(include_bootstrap=False)
    registry.register(FakeProvider())
    decision = IntelligenceRouter(registry, telemetry_path=telemetry).select("coding", complexity=0.5)
    assert decision.provider.name == "measured-provider"
    assert decision.profile.resource_cost == 0.2
    assert "profile=measured:3" in decision.reason
