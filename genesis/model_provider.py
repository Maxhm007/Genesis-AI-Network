from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from .model_lab import ModelLab, ModelLineage


_ALLOWED_CAPABILITIES = frozenset({"reasoning", "coding", "research", "planning", "review"})
_RUNTIME_KIND = "local_transformers_causal_lm"
_MODEL_ARTIFACT_ROOT = Path("runtime/model_artifacts")
_TRAINING_PROVENANCE_TYPE = "training_provenance"


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _normalized_hashes(value: object) -> dict[str, str] | None:
    if not isinstance(value, dict) or not value:
        return None
    result: dict[str, str] = {}
    for raw_name, raw_hash in value.items():
        name = str(raw_name).strip()
        digest = str(raw_hash).strip().lower()
        if not name or len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest):
            return None
        result[name] = digest
    return result


class ActiveGenesisModelProvider:
    """Lazy local provider backed only by an independently activated Genesis model.

    Model Lab activation alone is not enough. Runtime evidence must explicitly
    identify a local Transformers causal-LM artifact under runtime/model_artifacts,
    declare the qualified capabilities, and bind every model weight file plus the
    config to an exact SHA-256. A separate training-provenance record must prove
    that Genesis produced new weights/adapters from the recorded base model and
    dataset and must bind to those same output hashes. The provider never
    downloads weights and never enables trust_remote_code.

    A Qwen base is allowed as ancestry only after this derivation proof exists;
    raw Qwen weights are not treated as a Genesis-owned model.
    """

    def __init__(self, root: Path, model: ModelLineage, runtime_evidence: dict[str, Any]) -> None:
        self.root = Path(root).resolve()
        self.model = model
        self.runtime_evidence = dict(runtime_evidence)
        self.name = f"genesis-active:{model.model_id}"
        self.capabilities = self._capabilities(runtime_evidence)
        self.resource_cost = max(0.05, float(model.resource_cost if model.resource_cost is not None else 1.0))
        self.reliability = 0.75
        self._availability_cache: bool | None = None
        self._tokenizer = None
        self._model = None
        self._torch = None

    @staticmethod
    def _capabilities(runtime_evidence: dict[str, Any]) -> tuple[str, ...]:
        raw = runtime_evidence.get("capabilities", [])
        if not isinstance(raw, list):
            return ()
        return tuple(
            sorted(
                {
                    str(item).strip().lower()
                    for item in raw
                    if str(item).strip().lower() in _ALLOWED_CAPABILITIES
                }
            )
        )

    @staticmethod
    def _training_provenance_valid(
        model: ModelLineage,
        evidence: list[dict[str, Any]],
        runtime_evidence: dict[str, Any],
    ) -> bool:
        runtime_hashes = _normalized_hashes(runtime_evidence.get("files"))
        if runtime_hashes is None:
            return False
        rows = [row for row in evidence if row.get("evidence_type") == _TRAINING_PROVENANCE_TYPE]
        if not rows:
            return False
        payload = rows[-1].get("payload")
        if not isinstance(payload, dict):
            return False
        if payload.get("produced_new_weights") is not True:
            return False
        if str(payload.get("output_model_id") or "").strip() != model.model_id:
            return False
        if str(payload.get("base_model") or "").strip() != model.base_model:
            return False
        if str(payload.get("method") or "").strip() != model.method:
            return False
        if str(payload.get("dataset_hash") or "").strip() != model.dataset_hash:
            return False
        output_hashes = _normalized_hashes(payload.get("files"))
        return output_hashes is not None and output_hashes == runtime_hashes

    @classmethod
    def discover(cls, root: Path) -> list["ActiveGenesisModelProvider"]:
        root = Path(root).resolve()
        lab = ModelLab(root)
        providers: list[ActiveGenesisModelProvider] = []
        for model in lab.list():
            if model.state != "active" or model.benchmark_score is None:
                continue
            evidence = lab.evidence(model.model_id)
            runtime_rows = [
                row
                for row in evidence
                if row.get("evidence_type") == "runtime"
            ]
            if not runtime_rows:
                continue
            runtime_evidence = dict(runtime_rows[-1].get("payload", {}) or {})
            if not cls._training_provenance_valid(model, evidence, runtime_evidence):
                continue
            provider = cls(root, model, runtime_evidence)
            if provider.available():
                providers.append(provider)
        providers.sort(key=lambda item: (item.resource_cost, item.name))
        return providers

    def _artifact_path(self) -> Path | None:
        if self.runtime_evidence.get("kind") != _RUNTIME_KIND:
            return None
        raw = str(self.runtime_evidence.get("artifact_path") or "").strip()
        if not raw:
            return None
        relative = Path(raw)
        if relative.is_absolute():
            return None
        artifact = (self.root / relative).resolve()
        allowed_root = (self.root / _MODEL_ARTIFACT_ROOT).resolve()
        try:
            artifact.relative_to(allowed_root)
        except ValueError:
            return None
        return artifact

    def _verified_files(self, artifact: Path) -> bool:
        expected = _normalized_hashes(self.runtime_evidence.get("files"))
        if expected is None or "config.json" not in expected:
            return False

        actual_weights = {
            path.name for path in artifact.glob("*.safetensors") if path.is_file()
        }
        if (artifact / "pytorch_model.bin").is_file():
            actual_weights.add("pytorch_model.bin")
        if not actual_weights or not actual_weights.issubset(set(expected)):
            return False

        for name, wanted in expected.items():
            relative = Path(name)
            if relative.is_absolute() or ".." in relative.parts:
                return False
            candidate = (artifact / relative).resolve()
            try:
                candidate.relative_to(artifact)
            except ValueError:
                return False
            if not candidate.is_file() or _sha256_file(candidate) != wanted:
                return False
        return True

    def available(self) -> bool:
        if self._availability_cache is not None:
            return self._availability_cache
        available = False
        if self.model.state == "active" and self.model.benchmark_score is not None and self.capabilities:
            artifact = self._artifact_path()
            if artifact is not None and artifact.is_dir() and (artifact / "config.json").is_file():
                available = self._verified_files(artifact)
        self._availability_cache = available
        return available

    def _load(self) -> None:
        if self._model is not None:
            return
        artifact = self._artifact_path()
        # Re-check hashes immediately before the first load. Availability may have
        # been cached during registry discovery, and the artifact must not be
        # swappable between admission and execution.
        if artifact is None or not self.available() or not self._verified_files(artifact):
            raise RuntimeError("active Genesis model runtime artifact is unavailable or failed integrity verification")
        try:
            import torch
            from transformers import AutoModelForCausalLM, AutoTokenizer
        except ImportError as exc:
            raise RuntimeError("local Genesis model runtime requires torch and transformers") from exc

        self._torch = torch
        self._tokenizer = AutoTokenizer.from_pretrained(
            str(artifact),
            local_files_only=True,
            trust_remote_code=False,
        )
        self._model = AutoModelForCausalLM.from_pretrained(
            str(artifact),
            local_files_only=True,
            trust_remote_code=False,
            torch_dtype="auto",
            low_cpu_mem_usage=True,
        )
        self._model.eval()

    def reason(self, prompt: str) -> str:
        prompt = str(prompt).strip()
        if not prompt:
            raise ValueError("prompt is required")
        self._load()
        assert self._tokenizer is not None
        assert self._model is not None
        assert self._torch is not None

        system = (
            "You are an independently validated Genesis local model capability. "
            "Return concise, testable, evidence-aware output and preserve Genesis safety and validation boundaries."
        )
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt[:14000]},
        ]
        try:
            text = self._tokenizer.apply_chat_template(
                messages,
                tokenize=False,
                add_generation_prompt=True,
                enable_thinking=False,
            )
        except TypeError:
            text = self._tokenizer.apply_chat_template(
                messages,
                tokenize=False,
                add_generation_prompt=True,
            )
        inputs = self._tokenizer(text, return_tensors="pt", truncation=True, max_length=4096)
        max_new_tokens = self.runtime_evidence.get("max_new_tokens", 384)
        try:
            max_new_tokens = max(64, min(int(max_new_tokens), 768))
        except (TypeError, ValueError):
            max_new_tokens = 384
        with self._torch.no_grad():
            output = self._model.generate(
                **inputs,
                max_new_tokens=max_new_tokens,
                do_sample=False,
                repetition_penalty=1.03,
                pad_token_id=self._tokenizer.eos_token_id,
            )
        prompt_tokens = inputs["input_ids"].shape[-1]
        response = self._tokenizer.decode(
            output[0][prompt_tokens:],
            skip_special_tokens=True,
        ).strip()
        if not response:
            raise RuntimeError("active Genesis model returned no response text")
        return response

    def status(self) -> dict[str, Any]:
        artifact = self._artifact_path()
        return {
            "name": self.name,
            "model_id": self.model.model_id,
            "base_model": self.model.base_model,
            "state": self.model.state,
            "benchmark_score": self.model.benchmark_score,
            "capabilities": list(self.capabilities),
            "artifact_path": None if artifact is None else str(artifact.relative_to(self.root)),
            "available": self.available(),
            "runtime_kind": self.runtime_evidence.get("kind"),
            "provider_independent": True,
            "remote_downloads_allowed": False,
            "artifact_hashes_required": True,
            "training_provenance_required": True,
            "genesis_owned_derivative": True,
            "qwen_foundation_allowed_after_derivation": True,
        }
