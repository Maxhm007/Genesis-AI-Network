from pathlib import Path

import pytest

from genesis.model_lab import ModelLab


def test_model_lab_records_lineage_and_blocks_unmeasured_promotion(tmp_path: Path) -> None:
    lab = ModelLab(tmp_path)
    model = lab.plan(
        name="genesis-coder-small",
        base_model="open-weight/base",
        method="distillation",
        dataset_ref="datasets/coder-v1.jsonl",
        dataset_hash="abc123",
    )
    assert model.state == "planned"
    assert lab.plan(
        name="genesis-coder-small",
        base_model="open-weight/base",
        method="distillation",
        dataset_ref="datasets/coder-v1.jsonl",
        dataset_hash="abc123",
    ).model_id == model.model_id

    assert lab.transition(model.model_id, "training").state == "training"
    assert lab.transition(model.model_id, "tested").state == "tested"
    with pytest.raises(ValueError):
        lab.transition(model.model_id, "validated", benchmark_score=0.81)

    lab.add_evidence(model.model_id, "benchmark", {"suite": "coding-v1", "score": 0.81})
    validated = lab.transition(model.model_id, "validated", benchmark_score=0.81, resource_cost=0.4)
    assert validated.benchmark_score == 0.81
    assert validated.resource_cost == 0.4
    assert lab.transition(model.model_id, "trusted").state == "trusted"

    with pytest.raises(ValueError, match="training provenance and runtime evidence"):
        lab.transition(model.model_id, "active")
    lab.add_evidence(model.model_id, "training_provenance", {"produced_new_weights": True})
    with pytest.raises(ValueError, match="runtime"):
        lab.transition(model.model_id, "active")
    lab.add_evidence(model.model_id, "runtime", {"kind": "local_transformers_causal_lm"})
    assert lab.transition(model.model_id, "active").state == "active"


def test_model_lab_rejects_lifecycle_skips_and_keeps_provenance(tmp_path: Path) -> None:
    lab = ModelLab(tmp_path)
    model = lab.plan(
        name="genesis-researcher",
        base_model="provider-neutral-base",
        method="fine_tune",
        dataset_ref="datasets/research-v1.jsonl",
        dataset_hash="def456",
    )
    with pytest.raises(ValueError):
        lab.transition(model.model_id, "active", benchmark_score=1.0)
    lab.add_evidence(model.model_id, "dataset_provenance", {"license": "approved", "source_count": 12})
    evidence = lab.evidence(model.model_id)
    assert evidence[0]["payload"]["source_count"] == 12
    rejected = lab.transition(model.model_id, "rejected")
    assert rejected.state == "rejected"
    status = lab.export_status()
    assert status["counts"]["rejected"] == 1
    assert "training provenance" in status["rule"]
    assert "runtime artifact" in status["rule"]


def _trusted_version(lab: ModelLab, *, name: str, dataset_hash: str, score: float) -> str:
    model = lab.plan(
        name=name,
        base_model="open-weight/base",
        method="distillation",
        dataset_ref=f"datasets/{dataset_hash}.jsonl",
        dataset_hash=dataset_hash,
    )
    lab.transition(model.model_id, "training")
    lab.transition(model.model_id, "tested")
    lab.add_evidence(model.model_id, "benchmark", {"suite": "coding-v1", "score": score})
    lab.transition(model.model_id, "validated", benchmark_score=score, resource_cost=0.2)
    lab.transition(model.model_id, "trusted")
    lab.add_evidence(model.model_id, "training_provenance", {"produced_new_weights": True})
    lab.add_evidence(
        model.model_id,
        "runtime",
        {"kind": "local_transformers_causal_lm", "artifact_sha256": dataset_hash},
    )
    return model.model_id


def test_model_lab_versions_are_explicit_and_prevent_silent_active_replacement(tmp_path: Path) -> None:
    lab = ModelLab(tmp_path)
    first_id = _trusted_version(lab, name="genesis-coder", dataset_hash="v1hash", score=0.81)
    second_id = _trusted_version(lab, name="genesis-coder", dataset_hash="v2hash", score=0.84)

    assert lab.transition(first_id, "active").state == "active"
    assert [item.model_id for item in lab.versions("genesis-coder")] == [first_id, second_id]
    assert lab.active("genesis-coder").model_id == first_id

    with pytest.raises(ValueError, match="use rollback"):
        lab.transition(second_id, "active")

    status = lab.export_status()
    assert status["active_by_name"] == {"genesis-coder": first_id}


def test_model_lab_rollback_atomically_activates_trusted_fallback_and_records_evidence(tmp_path: Path) -> None:
    lab = ModelLab(tmp_path)
    current_id = _trusted_version(lab, name="genesis-coder", dataset_hash="current", score=0.90)
    fallback_id = _trusted_version(lab, name="genesis-coder", dataset_hash="fallback", score=0.86)
    lab.transition(current_id, "active")

    fallback = lab.rollback(
        current_id,
        fallback_id,
        reason="post-activation regression on coding benchmark",
    )

    assert fallback.state == "active"
    assert lab.get(current_id).state == "rejected"
    assert lab.active("genesis-coder").model_id == fallback_id

    source_evidence = lab.evidence(current_id)
    fallback_evidence = lab.evidence(fallback_id)
    assert source_evidence[-1]["evidence_type"] == "rollback"
    assert source_evidence[-1]["payload"]["fallback_model_id"] == fallback_id
    assert fallback_evidence[-1]["evidence_type"] == "rollback_activation"
    assert fallback_evidence[-1]["payload"]["replaced_model_id"] == current_id


def test_model_lab_rollback_refuses_untrusted_or_cross_family_fallback(tmp_path: Path) -> None:
    lab = ModelLab(tmp_path)
    current_id = _trusted_version(lab, name="genesis-coder", dataset_hash="current", score=0.90)
    lab.transition(current_id, "active")

    untrusted = lab.plan(
        name="genesis-coder",
        base_model="open-weight/base",
        method="distillation",
        dataset_ref="datasets/untrusted.jsonl",
        dataset_hash="untrusted",
    )
    with pytest.raises(ValueError, match="must already be trusted"):
        lab.rollback(current_id, untrusted.model_id, reason="test")

    other_family_id = _trusted_version(lab, name="genesis-researcher", dataset_hash="other", score=0.88)
    with pytest.raises(ValueError, match="same model family"):
        lab.rollback(current_id, other_family_id, reason="test")

    with pytest.raises(ValueError, match="reason is required"):
        lab.rollback(current_id, other_family_id, reason="   ")
