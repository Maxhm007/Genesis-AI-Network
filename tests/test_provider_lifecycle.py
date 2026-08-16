from pathlib import Path

import pytest

from genesis.provider_lifecycle import ProviderCandidate, ProviderTrustRegistry


def candidate(state: str = "QUARANTINED") -> ProviderCandidate:
    return ProviderCandidate(
        provider_id="demo",
        provider_type="local-open-weight",
        model_id="demo/model",
        state=state,
        source="https://example.invalid/demo",
        license="apache-2.0",
        capabilities=["advanced_reasoning"],
    )


def test_provider_cannot_skip_trust_states(tmp_path: Path):
    registry = ProviderTrustRegistry(tmp_path / "providers.json")
    registry.register(candidate())
    with pytest.raises(ValueError):
        registry.transition("demo", "ACTIVE", {"result": "pass"})


def test_provider_requires_evidence_to_advance(tmp_path: Path):
    registry = ProviderTrustRegistry(tmp_path / "providers.json")
    registry.register(candidate())
    with pytest.raises(ValueError):
        registry.transition("demo", "TESTED")


def test_provider_can_advance_and_persist(tmp_path: Path):
    path = tmp_path / "providers.json"
    registry = ProviderTrustRegistry(path)
    registry.register(candidate())
    registry.transition("demo", "TESTED", {"benchmark": "pass"})
    registry.transition("demo", "VALIDATED", {"independent_quorum": "pass"})
    registry.transition("demo", "TRUSTED", {"policy_review": "pass"})
    registry.transition("demo", "ACTIVE", {"activation": "approved"})
    registry.save()

    loaded = ProviderTrustRegistry(path)
    assert loaded.get("demo").state == "ACTIVE"
    assert len(loaded.get("demo").evidence) == 4
    assert len(loaded.active()) == 1


def test_active_provider_can_be_demoted_to_quarantine(tmp_path: Path):
    registry = ProviderTrustRegistry(tmp_path / "providers.json")
    registry.register(candidate("ACTIVE"))
    registry.transition("demo", "QUARANTINED", {"reason": "regression"})
    assert registry.get("demo").state == "QUARANTINED"
