from pathlib import Path
from types import SimpleNamespace

import pytest

from genesis.model_training import LocalLoraSubprocessBackend, TrainingBudget


def test_cpu_backend_rejects_invalid_device(tmp_path):
    with pytest.raises(ValueError):
        LocalLoraSubprocessBackend(tmp_path, device="tpu")


def test_cpu_backend_enforces_budget_before_training(tmp_path):
    base = tmp_path / "base"
    base.mkdir()
    with pytest.raises(ValueError, match="CPU training budget"):
        LocalLoraSubprocessBackend(tmp_path, device="cpu").run(
            base_path=base,
            dataset_path=tmp_path / "train.jsonl",
            output_dir=tmp_path / "output",
            budget=TrainingBudget(max_steps=21, max_sequence_length=512, lora_rank=8),
        )


def test_cpu_backend_rejects_large_checkpoint(tmp_path):
    base = tmp_path / "base"
    base.mkdir()
    with (base / "weights.bin").open("wb") as handle:
        handle.truncate(401 * 1024 * 1024)
    with pytest.raises(ValueError, match="400 MiB"):
        LocalLoraSubprocessBackend(tmp_path, device="cpu").run(
            base_path=base,
            dataset_path=tmp_path / "train.jsonl",
            output_dir=tmp_path / "output",
            budget=TrainingBudget(max_steps=2, max_sequence_length=256, lora_rank=4),
        )
