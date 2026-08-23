from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from genesis.intelligence_router import IntelligenceRouter
from genesis.model_lab import ModelLab
from genesis.model_provider import ActiveGenesisModelProvider
from genesis.providers import ProviderRegistry


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _activate_model(
    root: Path,
    *,
    base_model: str = "open-weight/base",
    capabilities: list[str] | None = None,
    tamper_hash: bool = False,
):
    lab = ModelLab(root)
    model = lab.plan(
        name="genesis-coder-local",
        base_model=base_model,
        method="distillation",
        dataset_ref="datasets/coder-v2.jsonl",
        dataset_hash="dataset-hash-v2",
    )
    lab.transition(model.model_id, "training")
    lab.transition(model.model_id, "tested")
    lab.add_evidence(model.model_id, "benchmark", {"suite": "coding-v2", "score": 0.82})
    lab.transition(model.model_id, "validated", benchmark_score=0.82, resource_cost=0.4)
    lab.transition(model.model_id, "trusted")
    model = lab.transition(model.model_id, "active")

    artifact = root / "runtime" / "model_artifacts" / model.model_id
    artifact.mkdir(parents=True)
    config = b'{"model_type":"test"}'
    weights = b"validated-local-weights"
    (artifact / "config.json").write_bytes(config)
    (artifact / "model.safetensors").write_bytes(weights)
    lab.add_evidence(
        model.model_id,
        "runtime",
        {
            "kind": "local_transformers_causal_lm",
            "artifact_path": str(artifact.relative_to(root)),
            "capabilities": capabilities or ["coding", "reasoning"],
            "max_new_tokens": 256,
            "files": {
                "config.json": _sha256(config),
                "model.safetensors": "0" * 64 if tamper_hash else _sha256(weights),
            },
        },
    )
    return model


def test_registry_discovers_only_integrity_bound_active_model(tmp_path: Path) -> None:
    model = _activate_model(tmp_path, capabilities=["coding"])

    registry = ProviderRegistry(include_bootstrap=False, root=tmp_path)
    available = registry.available_providers()

    assert registry.discovery_errors() == ()
    assert [provider.name for provider in available] == [f"genesis-active:{model.model_id}"]
    provider = available[0]
    assert provider.capabilities == ("coding",)
    assert provider.status()["artifact_hashes_required"] is True
    assert provider.status()["remote_downloads_allowed"] is False


def test_wrong_runtime_hash_is_not_admitted(tmp_path: Path) -> None:
    _activate_model(tmp_path, tamper_hash=True)

    registry = ProviderRegistry(include_bootstrap=False, root=tmp_path)

    assert registry.available_providers() == []
    assert registry.discovery_errors() == ()


def test_qwen_derived_active_model_remains_excluded_by_owner_policy(tmp_path: Path) -> None:
    _activate_model(tmp_path, base_model="Qwen/Qwen3-0.6B")

    registry = ProviderRegistry(include_bootstrap=False, root=tmp_path)

    assert registry.available_providers() == []


def test_active_model_without_runtime_evidence_is_not_a_provider(tmp_path: Path) -> None:
    lab = ModelLab(tmp_path)
    model = lab.plan(
        name="genesis-no-runtime",
        base_model="open-weight/base",
        method="fine_tune",
        dataset_ref="datasets/grounded.jsonl",
        dataset_hash="grounded-hash",
    )
    lab.transition(model.model_id, "training")
    lab.transition(model.model_id, "tested")
    lab.add_evidence(model.model_id, "benchmark", {"suite": "reasoning-v1", "score": 0.8})
    lab.transition(model.model_id, "validated", benchmark_score=0.8)
    lab.transition(model.model_id, "trusted")
    lab.transition(model.model_id, "active")

    assert ActiveGenesisModelProvider.discover(tmp_path) == []


def test_router_respects_qualified_model_capabilities(tmp_path: Path) -> None:
    _activate_model(tmp_path, capabilities=["coding"])
    registry = ProviderRegistry(include_bootstrap=False, root=tmp_path)
    router = IntelligenceRouter(registry)

    coding = router.select("coding", complexity=0.7)
    assert coding.profile.capabilities == ("coding",)
    assert coding.provider.name.startswith("genesis-active:")

    with pytest.raises(RuntimeError, match="no suitable intelligence provider for research"):
        router.select("research", complexity=0.1)


def test_runtime_artifact_must_stay_under_model_artifact_root(tmp_path: Path) -> None:
    model = _activate_model(tmp_path)
    lab = ModelLab(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    config = b"{}"
    weights = b"weights"
    (outside / "config.json").write_bytes(config)
    (outside / "model.safetensors").write_bytes(weights)
    lab.add_evidence(
        model.model_id,
        "runtime",
        {
            "kind": "local_transformers_causal_lm",
            "artifact_path": "outside",
            "capabilities": ["coding"],
            "files": {
                "config.json": _sha256(config),
                "model.safetensors": _sha256(weights),
            },
        },
    )

    assert ActiveGenesisModelProvider.discover(tmp_path) == []
