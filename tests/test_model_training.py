from __future__ import annotations

import json
from pathlib import Path

import pytest

from genesis.model_lab import ModelLab
from genesis.model_training import (
    MAX_STEPS,
    ModelTrainingLane,
    TrainingBudget,
    TrainingRequest,
    sha256_file,
)


class FakeTrainingBackend:
    name = "fake_training_backend"

    def __init__(self, *, ready: bool = True, fail: bool = False) -> None:
        self.ready = ready
        self.fail = fail
        self.calls = 0

    def probe(self):
        return {
            "ready": self.ready,
            "missing": [] if self.ready else ["cuda_gpu"],
            "backend": self.name,
            "requires_self_hosted_compute": True,
        }

    def run(self, *, base_path, dataset_path, output_dir, budget):
        self.calls += 1
        if self.fail:
            raise RuntimeError("synthetic training failure")
        (output_dir / "config.json").write_text('{"model_type":"genesis-test"}', encoding="utf-8")
        (output_dir / "model.safetensors").write_bytes(b"new-genesis-derived-weights")
        (output_dir / "tokenizer_config.json").write_text("{}", encoding="utf-8")
        return {"backend": self.name, "examples_seen": 1}


def _fixture(tmp_path: Path, *, base_model: str = "Qwen/Qwen3-0.6B"):
    base_root = tmp_path / "runtime" / "model_bases"
    dataset_root = tmp_path / "runtime" / "model_datasets"
    base = base_root / "qwen-local"
    base.mkdir(parents=True)
    (base / "config.json").write_text('{"model_type":"qwen3"}', encoding="utf-8")
    (base / "model.safetensors").write_bytes(b"local-foundation-weights")

    dataset_root.mkdir(parents=True)
    dataset = dataset_root / "coder.jsonl"
    dataset.write_text(
        json.dumps({"prompt": "Return one safe edit.", "response": "Use the smallest tested change."}) + "\n",
        encoding="utf-8",
    )
    dataset_hash = sha256_file(dataset)

    lab = ModelLab(tmp_path)
    model = lab.plan(
        name="genesis-coder-v1",
        base_model=base_model,
        method="lora",
        dataset_ref="runtime/model_datasets/coder.jsonl",
        dataset_hash=dataset_hash,
    )
    request = TrainingRequest(
        model_id=model.model_id,
        base_path="qwen-local",
        dataset_path="coder.jsonl",
        capabilities=("coding", "reasoning"),
        budget=TrainingBudget(max_steps=4, max_examples=8, max_output_bytes=1024 * 1024),
    )
    return lab, model, request, base, dataset


def test_readiness_requires_real_compute_backend(tmp_path: Path) -> None:
    _, _, request, _, _ = _fixture(tmp_path)
    backend = FakeTrainingBackend(ready=False)
    lane = ModelTrainingLane(tmp_path, backend=backend)

    readiness = lane.readiness(request)

    assert readiness["ready"] is False
    assert "cuda_gpu" in readiness["missing"]
    assert readiness["auto_activation"] is False
    assert backend.calls == 0


def test_dataset_hash_must_match_model_lab_lineage(tmp_path: Path) -> None:
    lab, model, request, _, dataset = _fixture(tmp_path)
    dataset.write_text('{"prompt":"changed","response":"changed"}\n', encoding="utf-8")
    lane = ModelTrainingLane(tmp_path, backend=FakeTrainingBackend())

    readiness = lane.readiness(request)

    assert readiness["ready"] is False
    assert any("dataset SHA-256" in error for error in readiness["errors"])
    assert lab.get(model.model_id).state == "planned"


def test_training_paths_cannot_escape_configured_roots(tmp_path: Path) -> None:
    _, _, request, _, _ = _fixture(tmp_path)
    outside = tmp_path / "outside.jsonl"
    outside.write_text('{"prompt":"x","response":"y"}\n', encoding="utf-8")
    escaped = TrainingRequest(
        model_id=request.model_id,
        base_path=request.base_path,
        dataset_path=str(outside),
        capabilities=request.capabilities,
        budget=request.budget,
    )

    readiness = ModelTrainingLane(tmp_path, backend=FakeTrainingBackend()).readiness(escaped)

    assert readiness["ready"] is False
    assert any("escapes" in error for error in readiness["errors"])


def test_resource_budget_is_hard_bounded(tmp_path: Path) -> None:
    _, _, request, _, _ = _fixture(tmp_path)
    excessive = TrainingRequest(
        model_id=request.model_id,
        base_path=request.base_path,
        dataset_path=request.dataset_path,
        capabilities=request.capabilities,
        budget=TrainingBudget(max_steps=MAX_STEPS + 1, max_output_bytes=1024 * 1024),
    )

    readiness = ModelTrainingLane(tmp_path, backend=FakeTrainingBackend()).readiness(excessive)

    assert readiness["ready"] is False
    assert any("max_steps" in error for error in readiness["errors"])


def test_successful_training_stops_at_tested_and_binds_provenance(tmp_path: Path) -> None:
    lab, model, request, _, _ = _fixture(tmp_path)
    backend = FakeTrainingBackend()
    lane = ModelTrainingLane(tmp_path, backend=backend)

    result = lane.run(request)

    assert result["status"] == "tested"
    assert result["auto_activation"] is False
    assert backend.calls == 1
    current = lab.get(model.model_id)
    assert current is not None
    assert current.state == "tested"
    assert current.benchmark_score is None

    evidence = lab.evidence(model.model_id)
    training = [row["payload"] for row in evidence if row["evidence_type"] == "training_provenance"][-1]
    runtime = [row["payload"] for row in evidence if row["evidence_type"] == "runtime"][-1]
    assert training["produced_new_weights"] is True
    assert training["base_model"] == "Qwen/Qwen3-0.6B"
    assert training["dataset_hash"] == model.dataset_hash
    assert training["files"] == runtime["files"] == result["artifact_files"]
    assert runtime["artifact_path"] == f"runtime/model_artifacts/{model.model_id}"
    assert set(runtime["capabilities"]) == {"coding", "reasoning"}

    with pytest.raises(ValueError):
        lab.transition(model.model_id, "active", benchmark_score=1.0)


def test_training_failure_is_recorded_without_false_tested_state(tmp_path: Path) -> None:
    lab, model, request, _, _ = _fixture(tmp_path)
    backend = FakeTrainingBackend(fail=True)
    lane = ModelTrainingLane(tmp_path, backend=backend)

    with pytest.raises(RuntimeError, match="synthetic training failure"):
        lane.run(request)

    current = lab.get(model.model_id)
    assert current is not None
    assert current.state == "training"
    evidence = lab.evidence(model.model_id)
    assert any(row["evidence_type"] == "training_failure" for row in evidence)
    assert not any(row["evidence_type"] == "training_provenance" for row in evidence)
    assert not (tmp_path / "runtime" / "model_artifacts" / model.model_id).exists()


def test_training_will_not_overwrite_existing_model_artifact(tmp_path: Path) -> None:
    _, model, request, _, _ = _fixture(tmp_path)
    final = tmp_path / "runtime" / "model_artifacts" / model.model_id
    final.mkdir(parents=True)
    (final / "sentinel.txt").write_text("keep", encoding="utf-8")
    lane = ModelTrainingLane(tmp_path, backend=FakeTrainingBackend())

    with pytest.raises(RuntimeError, match="will not overwrite"):
        lane.run(request)

    assert (final / "sentinel.txt").read_text(encoding="utf-8") == "keep"
