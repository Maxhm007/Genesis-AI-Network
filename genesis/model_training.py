from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Any, Protocol

from .model_lab import ModelLab, ModelLineage


SUPPORTED_METHODS = frozenset({"lora", "peft_lora", "fine_tune_lora"})
ALLOWED_CAPABILITIES = frozenset({"reasoning", "coding", "research", "planning", "review"})
MAX_STEPS = 2_000
MAX_EXAMPLES = 50_000
MAX_SEQUENCE_LENGTH = 4_096
MAX_WALL_SECONDS = 28_800
MAX_OUTPUT_BYTES = 32 * 1024 * 1024 * 1024
MAX_DATASET_BYTES = 2 * 1024 * 1024 * 1024


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def directory_size(path: Path) -> int:
    return sum(item.stat().st_size for item in path.rglob("*") if item.is_file())


def hash_artifact_files(path: Path) -> dict[str, str]:
    return {
        item.relative_to(path).as_posix(): sha256_file(item)
        for item in sorted(path.rglob("*"))
        if item.is_file()
    }


def _inside(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


@dataclass(frozen=True)
class TrainingBudget:
    max_steps: int = 100
    max_examples: int = 2_000
    max_sequence_length: int = 2_048
    wall_seconds: int = 7_200
    max_output_bytes: int = 8 * 1024 * 1024 * 1024
    learning_rate: float = 2e-4
    gradient_accumulation_steps: int = 8
    lora_rank: int = 16
    lora_alpha: int = 32

    def validate(self) -> None:
        integer_limits = {
            "max_steps": (self.max_steps, 1, MAX_STEPS),
            "max_examples": (self.max_examples, 1, MAX_EXAMPLES),
            "max_sequence_length": (self.max_sequence_length, 128, MAX_SEQUENCE_LENGTH),
            "wall_seconds": (self.wall_seconds, 60, MAX_WALL_SECONDS),
            "max_output_bytes": (self.max_output_bytes, 1024 * 1024, MAX_OUTPUT_BYTES),
            "gradient_accumulation_steps": (self.gradient_accumulation_steps, 1, 128),
            "lora_rank": (self.lora_rank, 1, 256),
            "lora_alpha": (self.lora_alpha, 1, 1024),
        }
        for name, (value, minimum, maximum) in integer_limits.items():
            if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
                raise ValueError(f"{name} must be between {minimum} and {maximum}")
        if not 1e-7 <= float(self.learning_rate) <= 0.1:
            raise ValueError("learning_rate must be between 1e-7 and 0.1")


@dataclass(frozen=True)
class TrainingRequest:
    model_id: str
    base_path: str
    dataset_path: str
    capabilities: tuple[str, ...]
    budget: TrainingBudget


class TrainingBackend(Protocol):
    name: str

    def probe(self) -> dict[str, Any]: ...

    def run(
        self,
        *,
        base_path: Path,
        dataset_path: Path,
        output_dir: Path,
        budget: TrainingBudget,
    ) -> dict[str, Any]: ...


class LocalLoraSubprocessBackend:
    """Run the built-in LoRA trainer in a bounded child process.

    Heavy ML libraries remain optional and are never installed by normal Genesis
    workflows. A real run requires an operator/self-hosted environment that has
    the separate model-training requirements installed and a CUDA GPU available.
    """

    name = "local_lora_subprocess"

    def __init__(self, root: Path) -> None:
        self.root = Path(root).resolve()

    def probe(self) -> dict[str, Any]:
        missing = [
            name
            for name in ("torch", "transformers", "peft", "accelerate", "safetensors")
            if importlib.util.find_spec(name) is None
        ]
        cuda_available = False
        if not missing:
            try:
                import torch

                cuda_available = bool(torch.cuda.is_available())
            except Exception:
                cuda_available = False
        if not cuda_available:
            missing.append("cuda_gpu")
        return {
            "ready": not missing,
            "missing": sorted(set(missing)),
            "backend": self.name,
            "requires_self_hosted_compute": True,
        }

    def run(
        self,
        *,
        base_path: Path,
        dataset_path: Path,
        output_dir: Path,
        budget: TrainingBudget,
    ) -> dict[str, Any]:
        log_dir = self.root / "runtime" / "model_training_logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / f"{output_dir.name}.log"
        command = [
            sys.executable,
            "-m",
            "genesis.model_training_backend",
            "--base-path",
            str(base_path),
            "--dataset-path",
            str(dataset_path),
            "--output-dir",
            str(output_dir),
            "--max-steps",
            str(budget.max_steps),
            "--max-examples",
            str(budget.max_examples),
            "--max-sequence-length",
            str(budget.max_sequence_length),
            "--learning-rate",
            str(budget.learning_rate),
            "--gradient-accumulation-steps",
            str(budget.gradient_accumulation_steps),
            "--lora-rank",
            str(budget.lora_rank),
            "--lora-alpha",
            str(budget.lora_alpha),
        ]
        env = os.environ.copy()
        env["PYTHONPATH"] = str(self.root) + os.pathsep + env.get("PYTHONPATH", "")
        try:
            with log_path.open("w", encoding="utf-8") as log:
                completed = subprocess.run(
                    command,
                    cwd=self.root,
                    env=env,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    check=False,
                    timeout=budget.wall_seconds,
                    text=True,
                )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(f"model training exceeded wall budget of {budget.wall_seconds}s") from exc
        if completed.returncode != 0:
            tail = ""
            try:
                tail = log_path.read_text(encoding="utf-8", errors="replace")[-4000:]
            except OSError:
                pass
            raise RuntimeError(f"model training backend failed with exit {completed.returncode}: {tail}")
        return {"backend": self.name, "log_path": str(log_path.relative_to(self.root))}


class ModelTrainingLane:
    """Bounded, provenance-first training lane for Genesis-owned checkpoints.

    The controller never downloads a base model, never accepts arbitrary shell
    commands, and never promotes beyond ``tested``. A separate benchmark and the
    existing independent validation/trust/activation path remain mandatory.
    """

    def __init__(
        self,
        root: Path,
        *,
        backend: TrainingBackend | None = None,
        base_root: Path | None = None,
        dataset_root: Path | None = None,
    ) -> None:
        self.root = Path(root).resolve()
        self.lab = ModelLab(self.root)
        self.base_root = (
            Path(base_root)
            if base_root is not None
            else Path(os.environ.get("GENESIS_MODEL_BASE_ROOT", self.root / "runtime" / "model_bases"))
        ).resolve()
        self.dataset_root = (
            Path(dataset_root)
            if dataset_root is not None
            else Path(os.environ.get("GENESIS_MODEL_DATASET_ROOT", self.root / "runtime" / "model_datasets"))
        ).resolve()
        self.artifact_root = (self.root / "runtime" / "model_artifacts").resolve()
        self.staging_root = (self.root / "runtime" / "model_training_staging").resolve()
        self.backend = backend or LocalLoraSubprocessBackend(self.root)

    @staticmethod
    def _capabilities(values: tuple[str, ...] | list[str]) -> tuple[str, ...]:
        result = tuple(sorted({str(value).strip().lower() for value in values if str(value).strip()}))
        if not result or any(value not in ALLOWED_CAPABILITIES for value in result):
            raise ValueError("capabilities must contain only qualified Genesis cognitive capabilities")
        return result

    @staticmethod
    def _resolve_under(root: Path, value: str) -> Path:
        raw = Path(str(value).strip())
        candidate = raw.resolve() if raw.is_absolute() else (root / raw).resolve()
        if not _inside(candidate, root):
            raise ValueError("training path escapes its configured root")
        return candidate

    @staticmethod
    def _dataset_summary(path: Path, max_examples: int) -> dict[str, Any]:
        if not path.is_file():
            raise ValueError("training dataset does not exist")
        size = path.stat().st_size
        if size <= 0 or size > MAX_DATASET_BYTES:
            raise ValueError("training dataset size is outside the allowed bounds")
        count = 0
        with path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, 1):
                if not line.strip():
                    continue
                try:
                    item = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise ValueError(f"training dataset line {line_number} is not valid JSON") from exc
                if not isinstance(item, dict):
                    raise ValueError(f"training dataset line {line_number} must be an object")
                prompt = str(item.get("prompt") or "").strip()
                response = str(item.get("response") or "").strip()
                if not prompt or not response:
                    raise ValueError(f"training dataset line {line_number} requires prompt and response")
                count += 1
                if count > max_examples:
                    raise ValueError("training dataset exceeds the requested example budget")
        if count == 0:
            raise ValueError("training dataset contains no usable examples")
        return {"examples": count, "bytes": size, "sha256": sha256_file(path)}

    @staticmethod
    def _base_summary(path: Path) -> dict[str, Any]:
        if not path.is_dir() or not (path / "config.json").is_file():
            raise ValueError("local base model directory with config.json is required")
        weights = sorted(path.glob("*.safetensors"))
        if (path / "pytorch_model.bin").is_file():
            weights.append(path / "pytorch_model.bin")
        if not weights:
            raise ValueError("local base model weights are required")
        files = [path / "config.json", *weights]
        return {
            "bytes": sum(item.stat().st_size for item in files),
            "files": {item.relative_to(path).as_posix(): sha256_file(item) for item in files},
        }

    def readiness(self, request: TrainingRequest) -> dict[str, Any]:
        missing: list[str] = []
        errors: list[str] = []
        model: ModelLineage | None = self.lab.get(request.model_id)
        try:
            request.budget.validate()
        except ValueError as exc:
            errors.append(str(exc))
        if model is None:
            errors.append("model_id is not registered in Model Lab")
        elif model.state not in {"planned", "training"}:
            errors.append("model must be planned or training")
        elif model.method not in SUPPORTED_METHODS:
            errors.append(f"unsupported training method: {model.method}")

        try:
            capabilities = self._capabilities(request.capabilities)
        except ValueError as exc:
            capabilities = ()
            errors.append(str(exc))

        dataset_path: Path | None = None
        dataset: dict[str, Any] | None = None
        try:
            dataset_path = self._resolve_under(self.dataset_root, request.dataset_path)
            dataset = self._dataset_summary(dataset_path, request.budget.max_examples)
            if model is not None and dataset["sha256"] != model.dataset_hash:
                errors.append("training dataset SHA-256 does not match Model Lab dataset_hash")
        except ValueError as exc:
            errors.append(str(exc))

        base_path: Path | None = None
        base: dict[str, Any] | None = None
        try:
            base_path = self._resolve_under(self.base_root, request.base_path)
            base = self._base_summary(base_path)
            if base["bytes"] > request.budget.max_output_bytes:
                errors.append("output byte budget is smaller than the local base checkpoint")
        except ValueError as exc:
            errors.append(str(exc))

        probe = self.backend.probe()
        if not probe.get("ready"):
            missing.extend(str(item) for item in probe.get("missing", []) if str(item).strip())

        return {
            "ready": not errors and not missing,
            "model_id": request.model_id,
            "model_state": None if model is None else model.state,
            "method": None if model is None else model.method,
            "base_path": None if base_path is None else str(base_path),
            "dataset_path": None if dataset_path is None else str(dataset_path),
            "base": base,
            "dataset": dataset,
            "capabilities": list(capabilities),
            "budget": asdict(request.budget),
            "backend": probe,
            "missing": sorted(set(missing)),
            "errors": errors,
            "will_stop_at": "tested",
            "auto_activation": False,
        }

    def run(self, request: TrainingRequest) -> dict[str, Any]:
        readiness = self.readiness(request)
        if not readiness["ready"]:
            return {"status": "not_ready", "readiness": readiness}

        model = self.lab.get(request.model_id)
        assert model is not None
        base_path = Path(str(readiness["base_path"]))
        dataset_path = Path(str(readiness["dataset_path"]))
        capabilities = tuple(readiness["capabilities"])
        if model.state == "planned":
            model = self.lab.transition(model.model_id, "training")

        final_dir = self.artifact_root / model.model_id
        staging_dir = self.staging_root / model.model_id
        if final_dir.exists():
            raise RuntimeError("model artifact already exists; training will not overwrite it")
        if staging_dir.exists():
            shutil.rmtree(staging_dir)
        staging_dir.mkdir(parents=True, exist_ok=False)

        try:
            backend_result = self.backend.run(
                base_path=base_path,
                dataset_path=dataset_path,
                output_dir=staging_dir,
                budget=request.budget,
            )
            output_size = directory_size(staging_dir)
            if output_size <= 0 or output_size > request.budget.max_output_bytes:
                raise RuntimeError("trained artifact violates output byte budget")
            if not (staging_dir / "config.json").is_file():
                raise RuntimeError("trained artifact is missing config.json")
            weights = list(staging_dir.glob("*.safetensors"))
            if (staging_dir / "pytorch_model.bin").is_file():
                weights.append(staging_dir / "pytorch_model.bin")
            if not weights:
                raise RuntimeError("trained artifact contains no loadable model weights")

            final_dir.parent.mkdir(parents=True, exist_ok=True)
            staging_dir.replace(final_dir)
            output_hashes = hash_artifact_files(final_dir)
            dataset = readiness["dataset"] or {}
            base = readiness["base"] or {}
            provenance = {
                "output_model_id": model.model_id,
                "base_model": model.base_model,
                "base_path": str(base_path),
                "base_files": base.get("files", {}),
                "method": model.method,
                "dataset_ref": model.dataset_ref,
                "dataset_path": str(dataset_path),
                "dataset_hash": model.dataset_hash,
                "dataset_examples": dataset.get("examples"),
                "produced_new_weights": True,
                "files": output_hashes,
                "budget": asdict(request.budget),
                "backend": backend_result,
            }
            runtime = {
                "kind": "local_transformers_causal_lm",
                "artifact_path": str(final_dir.relative_to(self.root)),
                "capabilities": list(capabilities),
                "max_new_tokens": min(768, max(128, request.budget.max_sequence_length // 4)),
                "files": output_hashes,
            }
            self.lab.add_evidence(model.model_id, "training_provenance", provenance)
            self.lab.add_evidence(model.model_id, "runtime", runtime)
            tested = self.lab.transition(model.model_id, "tested")
            return {
                "status": "tested",
                "model": tested.as_dict(),
                "artifact_path": runtime["artifact_path"],
                "artifact_bytes": output_size,
                "artifact_files": output_hashes,
                "backend": backend_result,
                "next_required": "independent benchmark evidence before validated/trusted/active",
                "auto_activation": False,
            }
        except Exception as exc:
            try:
                self.lab.add_evidence(
                    model.model_id,
                    "training_failure",
                    {"error": f"{type(exc).__name__}: {exc}"[:4000], "budget": asdict(request.budget)},
                )
            except Exception:
                pass
            if staging_dir.exists():
                shutil.rmtree(staging_dir, ignore_errors=True)
            raise
