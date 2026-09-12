from pathlib import Path

from genesis.model_scout import ModelScoutModule
from genesis.provider_lifecycle import ProviderTrustRegistry


ROOT = Path(__file__).resolve().parents[1]
MODEL = "deepseek-ai/DeepSeek-R1-Distill-Qwen-1.5B"
PROVIDER_ID = "deepseek-r1-distill-qwen-1.5b-optional"


def test_deepseek_is_registered_as_gene0_model_candidate():
    candidates = ModelScoutModule().load_seed_candidates(ROOT / "config/model_candidates.json")
    matching = [candidate for candidate in candidates if candidate.name == MODEL]

    assert len(matching) == 1
    candidate = matching[0]
    assert candidate.license == "mit"
    assert candidate.state == "discovered"
    assert candidate.benchmark_score is None
    assert {"reasoning", "coding", "planning", "review"} <= set(candidate.capabilities)


def test_deepseek_provider_is_optional_and_not_active_before_validation():
    registry = ProviderTrustRegistry(ROOT / "config/provider_candidates.json")
    provider = registry.get(PROVIDER_ID)

    assert provider is not None
    assert provider.model_id == MODEL
    assert provider.state == "DISCOVERED"
    assert provider.evidence == []
    assert provider.metadata["optional"] is True
    assert provider.metadata["gene_scope"] == "gene-node-1"
    assert provider.metadata["activation_requires_independent_benchmark"] is True
    assert provider.metadata["trust_remote_code"] is False
    assert provider.provider_id not in {item.provider_id for item in registry.active()}


def test_existing_qwen_provider_remains_active():
    registry = ProviderTrustRegistry(ROOT / "config/provider_candidates.json")
    qwen = registry.get("qwen3-0.6b-local")

    assert qwen is not None
    assert qwen.state == "ACTIVE"
