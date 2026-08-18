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
    assert "cannot self-promote" in status["rule"]
