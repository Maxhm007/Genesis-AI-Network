"""Run a small CPU-only, independently gated training experiment.

This is an experimental Model Lab benchmark, never a model promotion.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from genesis.model_lab import ModelLab
from genesis.model_training import (
    LocalLoraSubprocessBackend, ModelTrainingLane,
    TrainingBudget, TrainingRequest, sha256_file,
)

ROOT = Path(__file__).resolve().parents[1]
MODEL_REPO = "HuggingFaceTB/SmolLM2-135M"


def score(model_path: Path, holdout: Path) -> float:
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer
    tokenizer = AutoTokenizer.from_pretrained(str(model_path), local_files_only=True, trust_remote_code=False)
    model = AutoModelForCausalLM.from_pretrained(str(model_path), local_files_only=True, trust_remote_code=False)
    model.eval()
    total, count = 0.0, 0
    with torch.no_grad():
        for line in holdout.read_text(encoding="utf-8").splitlines()[:12]:
            row = json.loads(line)
            text = str(row["prompt"]) + "\n" + str(row["response"])
            encoded = tokenizer(text, return_tensors="pt", truncation=True, max_length=256)
            if encoded["input_ids"].shape[1] < 2:
                continue
            output = model(**encoded, labels=encoded["input_ids"])
            total += float(output.loss.item())
            count += 1
    del model
    if not count:
        raise ValueError("holdout contains no scoreable examples")
    return total / count


def run(train: Path, holdout: Path) -> dict:
    import torch
    from huggingface_hub import snapshot_download

    report_root = ROOT / "runtime" / "cpu_experiment"
    report_root.mkdir(parents=True, exist_ok=True)
    if not train.is_file() or not holdout.is_file():
        raise FileNotFoundError("verified train and holdout splits are required")
    train_rows = [json.loads(line) for line in train.read_text(encoding="utf-8").splitlines() if line.strip()]
    holdout_rows = [json.loads(line) for line in holdout.read_text(encoding="utf-8").splitlines() if line.strip()]
    if len(train_rows) < 24 or len(holdout_rows) < 6:
        raise ValueError("insufficient train/holdout examples")
    train_ids = {row["provenance"]["promoted_commit"] for row in train_rows}
    test_ids = {row["provenance"]["promoted_commit"] for row in holdout_rows}
    if train_ids & test_ids:
        raise ValueError("training and benchmark contain overlapping commits")
    if any(row["provenance"].get("classification") != "genesis_autonomous_validated_promotion" for row in train_rows + holdout_rows):
        raise ValueError("unverified example in experiment")

    base_path = ROOT / "runtime" / "model_bases" / "smollm2-135m"
    base_path.mkdir(parents=True, exist_ok=True)
    snapshot_download(
        repo_id=MODEL_REPO,
        local_dir=str(base_path),
        allow_patterns=["*.json", "*.safetensors", "tokenizer.*", "*.model", "*.txt"],
    )
    if sum(p.stat().st_size for p in base_path.rglob("*") if p.is_file()) > 400 * 1024 * 1024:
        raise ValueError("downloaded base checkpoint exceeds CPU policy")
    print("Scoring base checkpoint on independent holdout", flush=True)
    baseline = score(base_path, holdout)
    lab = ModelLab(ROOT)
    item = lab.plan(
        name="genesis-cpu-smollm2-experiment", base_model=MODEL_REPO,
        method="lora", dataset_ref=str(train.relative_to(ROOT)),
        dataset_hash=sha256_file(train),
    )
    request = TrainingRequest(
        model_id=item.model_id,
        base_path=base_path.name,
        dataset_path=train.name,
        capabilities=("coding",),
        budget=TrainingBudget(max_steps=5, max_examples=64, max_sequence_length=256,
                              wall_seconds=720, max_output_bytes=400 * 1024 * 1024,
                              gradient_accumulation_steps=2, lora_rank=4, lora_alpha=8),
    )
    lane = ModelTrainingLane(ROOT, backend=LocalLoraSubprocessBackend(ROOT, device="cpu"))
    readiness = lane.readiness(request)
    if not readiness["ready"]:
        raise RuntimeError("CPU Model Lab not ready: " + json.dumps(readiness))
    trained = lane.run(request)
    if trained.get("status") != "tested":
        raise RuntimeError("training did not reach tested state: " + json.dumps(trained))
    artifact_path = ROOT / "runtime" / "model_artifacts" / item.model_id
    after = score(artifact_path, holdout)
    report = {
        "status": "cpu_training_experiment_completed",
        "base_model": MODEL_REPO,
        "training_examples": len(train_rows),
        "holdout_examples": len(holdout_rows),
        "train_sha256": sha256_file(train),
        "holdout_sha256": sha256_file(holdout),
        "baseline_holdout_loss": baseline,
        "trained_holdout_loss": after,
        "improved_holdout_loss": after < baseline,
        "training_device": "cpu",
        "automatic_activation": False,
        "model_lab_state": "tested",
        "quality_claim": "none; limited holdout loss is not proof of coding improvement",
    }
    (report_root / "benchmark.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--train", type=Path, required=True)
    parser.add_argument("--holdout", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.train.resolve(), args.holdout.resolve()), sort_keys=True))


if __name__ == "__main__":
    main()
