from pathlib import Path

from genesis.model_scout import ModelScoutModule
from genesis.provider_lifecycle import ProviderTrustRegistry


ROOT = Path(__file__).resolve().parents[1]
MODEL = "Qwen/Qwen3-4B-Instruct-2507"


def test_additional_qwen3_is_discovered_not_approved_for_activation():
    scout = ModelScoutModule()
    candidates = scout.load_seed_candidates(ROOT / "config/model_candidates.json")
    matching = [candidate for candidate in candidates if candidate.name == MODEL]
    assert len(matching) == 1
    model = matching[0]
    assert model.state == "discovered"
    assert model.benchmark_score is None
    assert model.license == "apache-2.0"
    assert "vision" not in model.capabilities
    assert scout.recommend(matching)[0].recommendation == "evaluate_next"


def test_existing_model_scout_candidates_are_retained():
    candidates = ModelScoutModule().load_seed_candidates(ROOT / "config/model_candidates.json")
    assert {"Qwen/Qwen3.5-2B", "Qwen/Qwen3.5-4B", "microsoft/Phi-4-mini-instruct"} <= {candidate.name for candidate in candidates}


def test_additional_provider_does_not_join_active_provider_set():
    registry = ProviderTrustRegistry(ROOT / "config/provider_candidates.json")
    additional = registry.get("qwen3-4b-instruct-2507-optional")
    assert additional is not None
    assert additional.model_id == MODEL
    assert additional.state == "DISCOVERED"
    assert additional.evidence == []
    assert additional.metadata["optional"] is True
    assert additional.metadata["activation_requires_independent_benchmark"] is True
    assert additional.metadata["trust_remote_code"] is False
    assert additional.provider_id not in {provider.provider_id for provider in registry.active()}
    existing = registry.get("qwen3-0.6b-local")
    assert existing is not None and existing.state == "ACTIVE"
    assert existing.metadata["benchmark_quorum_run"] == 31959538090
