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


def _prepare_model(
    root: Path,
    *,
    base_model: str = "open-weight/base",
    capabilities: list[str] | None = None,
    tamper_hash: bool = False,
    include_training_provenance: bool = True,
    include_runtime: bool = True,
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

    artifact = root / "runtime" / "model_artifacts" / model.model_id
    artifact.mkdir(parents=True)
    config = b'{"model_type":"test"}'
    weights = b"validated-local-weights"
    (artifact / "config.json").write_bytes(config)
    (artifact / "model.safetensors").write_bytes(weights)
    files = {
        "config.json": _sha256(config),
        "model.safetensors": "0" * 64 if tamper_hash else _sha256(weights),
    }
    if include_training_provenance:
        lab.add_evidence(
            model.model_id,
            "training_provenance",
            {
                "output_model_id": model.model_id,
                "base_model": model.base_model,
                "method": model.method,
                "dataset_hash": model.dataset_hash,
                "produced_new_weights": True,
                "files": files,
            },
        )
    if include_runtime:
        lab.add_evidence(
            model.model_id,
            "runtime",
            {
                "kind": "local_transformers_causal_lm",
                "artifact_path": str(artifact.relative_to(root)),
                "capabilities": capabilities or ["coding", "reasoning"],
                "max_new_tokens": 256,
                "files": files,
            },
        )
    return lab, model, artifact, files


def _activate_model(root: Path, **kwargs):
    lab, model, artifact, files = _prepare_model(root, **kwargs)
    model = lab.transition(model.model_id, "active")
    return lab, model, artifact, files


def test_registry_discovers_only_integrity_bound_active_model(tmp_path: Path) -> None:
    _, model, _, _ = _activate_model(tmp_path, capabilities=["coding"])

    registry = ProviderRegistry(include_bootstrap=False, root=tmp_path)
    available = registry.available_providers()

    assert registry.discovery_errors() == ()
    assert [provider.name for provider in available] == [f"genesis-active:{model.model_id}"]
    provider = available[0]
    assert provider.capabilities == ("coding",)
    assert provider.status()["artifact_hashes_required"] is True
    assert provider.status()["training_provenance_required"] is True
    assert provider.status()["remote_downloads_allowed"] is False


def test_wrong_runtime_hash_is_not_admitted(tmp_path: Path) -> None:
    _activate_model(tmp_path, tamper_hash=True)

    registry = ProviderRegistry(include_bootstrap=False, root=tmp_path)

    assert registry.available_providers() == []
    assert registry.discovery_errors() == ()


def test_qwen_derived_model_is_allowed_only_after_genesis_derivation_proof(tmp_path: Path) -> None:
    _, model, _, _ = _activate_model(tmp_path, base_model="Qwen/Qwen3-0.6B")

    registry = ProviderRegistry(include_bootstrap=False, root=tmp_path)
    available = registry.available_providers()

    assert [provider.name for provider in available] == [f"genesis-active:{model.model_id}"]
    status = available[0].status()
    assert status["base_model"] == "Qwen/Qwen3-0.6B"
    assert status["genesis_owned_derivative"] is True
    assert status["qwen_foundation_allowed_after_derivation"] is True


def test_model_without_training_provenance_cannot_become_active(tmp_path: Path) -> None:
    lab, model, _, _ = _prepare_model(tmp_path, include_training_provenance=False)

    with pytest.raises(ValueError, match="training provenance"):
        lab.transition(model.model_id, "active")
    assert ProviderRegistry(include_bootstrap=False, root=tmp_path).available_providers() == []


def test_qwen_base_without_training_provenance_cannot_become_genesis_model(tmp_path: Path) -> None:
    lab, model, _, _ = _prepare_model(
        tmp_path,
        base_model="Qwen/Qwen3-0.6B",
        include_training_provenance=False,
    )

    with pytest.raises(ValueError, match="training provenance"):
        lab.transition(model.model_id, "active")
    assert ProviderRegistry(include_bootstrap=False, root=tmp_path).available_providers() == []


def test_model_without_runtime_evidence_cannot_become_active(tmp_path: Path) -> None:
    lab, model, _, _ = _prepare_model(tmp_path, include_runtime=False)

    with pytest.raises(ValueError, match="runtime"):
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
    lab, model, _, _ = _prepare_model(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    config = b"{}"
    weights = b"weights"
    (outside / "config.json").write_bytes(config)
    (outside / "model.safetensors").write_bytes(weights)
    files = {
        "config.json": _sha256(config),
        "model.safetensors": _sha256(weights),
    }
    lab.add_evidence(
        model.model_id,
        "training_provenance",
        {
            "output_model_id": model.model_id,
            "base_model": model.base_model,
            "method": model.method,
            "dataset_hash": model.dataset_hash,
            "produced_new_weights": True,
            "files": files,
        },
    )
    lab.add_evidence(
        model.model_id,
        "runtime",
        {
            "kind": "local_transformers_causal_lm",
            "artifact_path": "outside",
            "capabilities": ["coding"],
            "files": files,
        },
    )
    lab.transition(model.model_id, "active")

    assert ActiveGenesisModelProvider.discover(tmp_path) == []


def test_training_provenance_hashes_must_match_runtime_artifact_hashes(tmp_path: Path) -> None:
    lab, model, artifact, runtime_files = _prepare_model(tmp_path)
    lab.add_evidence(
        model.model_id,
        "training_provenance",
        {
            "output_model_id": model.model_id,
            "base_model": model.base_model,
            "method": model.method,
            "dataset_hash": model.dataset_hash,
            "produced_new_weights": True,
            "files": {**runtime_files, "model.safetensors": "f" * 64},
        },
    )
    lab.add_evidence(
        model.model_id,
        "runtime",
        {
            "kind": "local_transformers_causal_lm",
            "artifact_path": str(artifact.relative_to(tmp_path)),
            "capabilities": ["coding"],
            "files": runtime_files,
        },
    )
    lab.transition(model.model_id, "active")

    assert ActiveGenesisModelProvider.discover(tmp_path) == []


def test_artifact_is_reverified_immediately_before_first_load(tmp_path: Path) -> None:
    _, model, artifact, _ = _activate_model(tmp_path)
    provider = ActiveGenesisModelProvider.discover(tmp_path)[0]
    assert provider.available() is True

    (artifact / "model.safetensors").write_bytes(b"swapped-after-admission")

    with pytest.raises(RuntimeError, match="failed integrity verification"):
        provider._load()
