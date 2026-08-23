from __future__ import annotations

from dataclasses import dataclass
from typing import Callable


INCUBATION_MARKER = "genesis-learning-new-capability-v1"


@dataclass(frozen=True)
class LearnedCapability:
    """One bounded executable capability learned from verified external evidence."""

    name: str
    description: str
    evidence: str
    handler: Callable[..., object]


_registry: dict[str, LearnedCapability] = {}


def register_capability(
    name: str,
    description: str,
    evidence: str,
    handler: Callable[..., object],
) -> LearnedCapability:
    """Register a learned capability without activating external side effects."""
    key = str(name).strip().lower().replace(" ", "_")
    if not key or not str(description).strip() or not str(evidence).strip():
        raise ValueError("learned capability requires name, description, and evidence")
    if not callable(handler):
        raise TypeError("learned capability handler must be callable")
    if key in _registry:
        raise ValueError(f"learned capability already registered: {key}")
    capability = LearnedCapability(
        name=key,
        description=str(description).strip(),
        evidence=str(evidence).strip(),
        handler=handler,
    )
    _registry[key] = capability
    return capability


def list_capabilities() -> tuple[LearnedCapability, ...]:
    return tuple(_registry[key] for key in sorted(_registry))


def run_capability(name: str, *args, **kwargs):
    key = str(name).strip().lower().replace(" ", "_")
    if key not in _registry:
        raise KeyError(key)
    return _registry[key].handler(*args, **kwargs)


def validate_registry() -> bool:
    return all(
        capability.name
        and capability.description
        and capability.evidence
        and callable(capability.handler)
        for capability in _registry.values()
    )


def _learned_2ab48edef009(
    reference_device: str | None,
    candidate_device: str | None,
    available,
) -> str | None:
    """Align generated candidate work to a known available runtime device."""
    choices = tuple(str(item).strip() for item in available if str(item).strip())
    reference = str(reference_device).strip() if reference_device is not None else ""
    candidate = str(candidate_device).strip() if candidate_device is not None else ""
    if reference and reference in choices:
        return reference
    if candidate and candidate in choices:
        return candidate
    return choices[0] if choices else None

register_capability(
    'runtime_device_alignment_2ab48edef009',
    'Align candidate/generated work to an available reference runtime device to avoid device-map mismatches. Verified lesson: Research-backed capability candidate from \'Patch release: v5.15.1\': # Patch release v5.15.1 This patch most notably solves a few issues with DFlash and MTP candidate generators, as well as an issue where images could sometimes not be processed on accelerator if using Lanczos filter. It contains the following commits: - Fix DFlash candidate token device mismatch with device_map="auto" (#47877) by @sywangyi and @Cyrilvallez - Align logit distributions for CandidateGenerators using sampling (#48007) by @Cyrilvallez - Fix MTP config when mlp_layer_types is absent (#48015) by @Cyrilvallez - Fallbac',
    '# Patch release v5.15.1 This patch most notably solves a few issues with DFlash and MTP candidate generators, as well as an issue where images could sometimes not be processed on accelerator if using Lanczos filter. It contains the following commits: - Fix DFlash candidate token device mismatch with device_map="auto" (#47877) by @sywangyi and @Cyrilvallez - Align logit distributions for CandidateGenerators using sampling (#48007) by @Cyrilvallez - Fix MTP config when mlp_layer_types is absent (#48015) by @Cyrilvallez - Fallback from \'lanczos\' to \'bicubic\' when on cuda (#48026) by @zucchini-nlp - Fix gemma4 video to device (#47896) by @guarin',
    _learned_2ab48edef009,
)


def _learned_1b55f2a58266(total: int, parts: int) -> tuple[int, ...]:
    """Split a non-negative tensor/work extent into balanced deterministic parts."""
    total_i = int(total)
    parts_i = int(parts)
    if total_i < 0 or parts_i < 1 or parts_i > 256:
        raise ValueError("tensor split inputs are out of bounds")
    base, extra = divmod(total_i, parts_i)
    return tuple(base + (1 if index < extra else 0) for index in range(parts_i))

register_capability(
    'balanced_tensor_split_1b55f2a58266',
    "Split a bounded tensor/work extent deterministically across multiple execution parts. Verified lesson: Research-backed capability candidate from 'v0.27.0': # vLLM v0.27.0 Release Notes ## Highlights This release features 561 commits from 242 contributors (64 new)! * **Kimi K3 support** with a full stack landing in one release: core model files and kernels (#50089, #50000), Python (#50093) and Rust (#50104) frontends, AttnRes kernels (#50090), DeepGEMM support (#50458), compressed-tensors quantized checkpoints (#50500), DSpark AR fusion (#50242), and an option to shard the shared expert instead of replicating it (#50656). * **More new models**: Qwen3.5 text-only dense and MoE models (#50210) wit",
    '# vLLM v0.27.0 Release Notes ## Highlights This release features 561 commits from 242 contributors (64 new)! * **Kimi K3 support** with a full stack landing in one release: core model files and kernels (#50089, #50000), Python (#50093) and Rust (#50104) frontends, AttnRes kernels (#50090), DeepGEMM support (#50458), compressed-tensors quantized checkpoints (#50500), DSpark AR fusion (#50242), and an option to shard the shared expert instead of replicating it (#50656). * **More new models**: Qwen3.5 text-only dense and MoE models (#50210) with EVS video token pruning (#48912), K-EXAONE-2.0-750B-A37B (#50524), VaultGemma via the Transformers modeling backend (#49803), and jina-embeddings-v5-text-nano (#50688). * **PyTorch 2.13.0 upgrade** along with torchvision 0.28.0 and Triton 3.7.1 (#48155) — this is a breaking environment change; XPU (#48677) and CPU (#50412) followed to torch 2.13 as well. * **FlashAttention 4 integration deepens on SM100**: FP8 KV cache support (#42569) and headdim-256 support (#42669), backed by a new JIT warmup infrastructure (#47451) and runner-owned Triton kernel warmup (#49903) that remove first-request compilation stalls. * **DeepSeek-V4 performance push*',
    _learned_1b55f2a58266,
)


# GENESIS_LEARNED_CAPABILITY_INSERTION_POINT
