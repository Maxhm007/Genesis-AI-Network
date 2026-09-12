from pathlib import Path
import pytest
from genesis.model_scout import ModelScoutModule
from genesis.provider_lifecycle import ProviderTrustRegistry
from scripts.github_qwen3_activation_probe import validate_code_response

ROOT = Path(__file__).resolve().parents[1]
MODEL = "Qwen/Qwen3-4B-Instruct-2507"


def test_additional_qwen3_requires_evidence_before_activation():
    scout = ModelScoutModule()
    candidates = scout.load_seed_candidates(ROOT / "config/model_candidates.json")
    matching = [candidate for candidate in candidates if candidate.name == MODEL]
    assert len(matching) == 1
    model = matching[0]
    assert model.license == "apache-2.0"
    assert "vision" not in model.capabilities
    if model.state == "discovered":
        assert model.benchmark_score is None
        assert scout.recommend(matching)[0].recommendation == "evaluate_next"
    else:
        assert model.state == "active"
        assert model.benchmark_score == 4
        assert scout.recommend(matching)[0].recommendation == "keep_active_and_monitor"


def test_existing_model_scout_candidates_are_retained():
    candidates = ModelScoutModule().load_seed_candidates(ROOT / "config/model_candidates.json")
    assert {"Qwen/Qwen3.5-2B", "Qwen/Qwen3.5-4B", "microsoft/Phi-4-mini-instruct"} <= {candidate.name for candidate in candidates}


def test_additional_provider_activation_requires_two_runner_evidence():
    registry = ProviderTrustRegistry(ROOT / "config/provider_candidates.json")
    additional = registry.get("qwen3-4b-instruct-2507-optional")
    assert additional is not None
    assert additional.model_id == MODEL
    assert additional.metadata["optional"] is True
    assert additional.metadata["activation_requires_independent_benchmark"] is True
    assert additional.metadata["trust_remote_code"] is False
    if additional.state == "DISCOVERED":
        assert additional.evidence == []
        assert additional.provider_id not in {p.provider_id for p in registry.active()}
    else:
        assert additional.state == "ACTIVE"
        benchmarks = [e for e in additional.evidence if e.get("kind") == "sandbox_benchmark"]
        assert {e["runner"] for e in benchmarks} == {"benchmark_a", "benchmark_b"}
        assert len({e["workflow_run"] for e in benchmarks}) == 1
        assert all(e["result"] == "pass" and e["artifact_digest"].startswith("sha256:") for e in benchmarks)
        assert {"QUARANTINED", "TESTED", "VALIDATED", "TRUSTED", "ACTIVE"} <= {e["state"] for e in additional.evidence}
    existing = registry.get("qwen3-0.6b-local")
    assert existing is not None and existing.state == "ACTIVE"
    assert existing.metadata["benchmark_quorum_run"] == 31959538090



def test_safe_minimal_generated_probe_passes():
    validate_code_response('{"files":{"genesis/probe.py":"def add(a, b):\\n    return a + b\\n"}}')


@pytest.mark.parametrize("response", [
    '{"files":{"genesis/probe.py":"import os\\ndef add(a,b): return a+b"}}',
    '{"files":{"genesis/probe.py":"def add(a,b): return a-b"}}',
    '{"files":{"genesis/other.py":"def add(a,b): return a+b"}}',
    '{"files":{"genesis/probe.py":"def add(a,b): return eval(a)"}}'
])
def test_unsafe_or_incorrect_generated_probes_fail(response):
    with pytest.raises((ValueError, SyntaxError)):
        validate_code_response(response)
