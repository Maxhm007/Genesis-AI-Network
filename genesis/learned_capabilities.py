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


def _learned_b3621110d8ad(items, limit: int = 64) -> tuple[object, ...]:
    """Retain the newest bounded linear-memory window without external side effects."""
    limit_i = int(limit)
    if limit_i < 1 or limit_i > 1024:
        raise ValueError("linear memory limit is out of bounds")
    values = tuple(items)
    return values[-limit_i:]

register_capability(
    'bounded_linear_memory_b3621110d8ad',
    "Maintain a bounded linear-memory window while preserving insertion order. Verified lesson: Research-backed capability candidate from 'python-v0.7.5': ## What's Changed * Fix docs dotnet core typo by @lach-g in https://github.com/microsoft/autogen/pull/6950 * Fix loading streaming Bedrock response with tool usage with empty argument by @pawel-dabro in https://github.com/microsoft/autogen/pull/6979 * Support linear memory in RedisMemory by @justin-cechmanek in https://github.com/microsoft/autogen/pull/6972 * Fix message ID for correlation between streaming chunks and final mes… by @smalltalkman in https://github.com/microsoft/autogen/pull/6969 * fix: extra args not work to disable t",
    "## What's Changed * Fix docs dotnet core typo by @lach-g in https://github.com/microsoft/autogen/pull/6950 * Fix loading streaming Bedrock response with tool usage with empty argument by @pawel-dabro in https://github.com/microsoft/autogen/pull/6979 * Support linear memory in RedisMemory by @justin-cechmanek in https://github.com/microsoft/autogen/pull/6972 * Fix message ID for correlation between streaming chunks and final mes… by @smalltalkman in https://github.com/microsoft/autogen/pull/6969 * fix: extra args not work to disable thinking by @liuyunrui123 in https://github.com/microsoft/autogen/pull/7006 * Add thinking mode support for anthropic client by @SrikarMannepalli in https://github.com/microsoft/autogen/pull/7002 * Fix spurious </think> tags caused by empty string reasoning_content in streaming by @Copilot in https://github.com/microsoft/autogen/pull/7025 * Fix GraphFlow cycle detection to properly clean up recursion state by @Copilot in https://github.com/microsoft/autogen/pull/7026 * Add comprehensive GitHub Copilot instructions for AutoGen development by @Copilot in https://github.com/microsoft/autogen/pull/7029 * Fix Redis caching always returning False due to unhand",
    _learned_b3621110d8ad,
)


def _learned_c7c0eb9aa26f(
    requested: str | None,
    available,
    fallback: str | None = None,
) -> str | None:
    """Prefer an explicit supported runtime device, then a compatible fallback."""
    choices = tuple(str(item).strip() for item in available if str(item).strip())
    preferred = str(requested).strip() if requested is not None else ""
    if preferred and preferred in choices:
        return preferred
    fallback_name = str(fallback).strip() if fallback is not None else ""
    if fallback_name and fallback_name in choices:
        return fallback_name
    return choices[0] if choices else None

register_capability(
    'runtime_device_selection_c7c0eb9aa26f',
    "Select an explicit supported runtime device while preserving a compatible fallback path. Verified lesson: Research-backed capability candidate from 'b10594': <details open> common : skip device_info loop if it's not going to be printed (#26692) The device_info loop iterates over the discovered devices and gets the available and total memory counts. With the CUDA backend (and possibly others too) this requires creating a GPU context, which, in case of CUDA, results in a 550 MB VRAM allocation. For this information to be used in any way, the log verbosity must be set to LOG_LEVEL_TRACE. If it's not, including in the default configuration, the contexts get created, memory sizes get queried, then the",
    "<details open> common : skip device_info loop if it's not going to be printed (#26692) The device_info loop iterates over the discovered devices and gets the available and total memory counts. With the CUDA backend (and possibly others too) this requires creating a GPU context, which, in case of CUDA, results in a 550 MB VRAM allocation. For this information to be used in any way, the log verbosity must be set to LOG_LEVEL_TRACE. If it's not, including in the default configuration, the contexts get created, memory sizes get queried, then the log function quietly discards the data. In certain cases the user may not want to use any GPU resources. The device_loop iteration is the only place touching the GPU that cannot be skipped. Fix by checking the verbosity level and skipping the loop if there would be no output. </details> **Website:** - <https://llama.app> **Attestations:** - <https://github.com/ggml-org/llama.cpp/attestations/42421792> **macOS/iOS:** - [macOS Apple Silicon (arm64)](https://github.com/ggml-org/llama.cpp/releases/download/b10594/llama-b10594-bin-macos-arm64.tar.gz) - macOS Apple Silicon (arm64, KleidiAI enabled) [DISABLED](https://github.com/ggml-org/llama.cpp/pul",
    _learned_c7c0eb9aa26f,
)


def learned_d00770f16537d2ca(self):
    # Your implementation here
    pass

def learned_8b7a22c14b8a383e(self):
    # Your implementation here
    pass

pass

def _learned_27322463c7e3(
    requested: str | None,
    available,
    fallback: str | None = None,
) -> str | None:
    """Prefer an explicit supported runtime device, then a compatible fallback."""
    choices = tuple(str(item).strip() for item in available if str(item).strip())
    preferred = str(requested).strip() if requested is not None else ""
    if preferred and preferred in choices:
        return preferred
    fallback_name = str(fallback).strip() if fallback is not None else ""
    if fallback_name and fallback_name in choices:
        return fallback_name
    return choices[0] if choices else None

register_capability(
    'runtime_device_selection_27322463c7e3',
    "Select an explicit supported runtime device while preserving a compatible fallback path. Verified lesson: Research-backed capability candidate from 'b10622': <details open> metal : null-check buffer alloc to fix OOM crash (#25371) * metal : null-check ggml_metal_buffer_init result to avoid OOM crash ggml_backend_metal_buffer_type_alloc_buffer used the result of ggml_metal_buffer_init without checking for NULL. ggml_metal_buffer_init returns NULL when the underlying Metal allocation fails (e.g. an out-of-memory condition), and the following ggml_metal_buffer_is_shared(res) call dereferences it, turning a recoverable allocation failure into a hard crash (EXC_BAD_ACCESS). This is easy to hit on memor",
    '<details open> metal : null-check buffer alloc to fix OOM crash (#25371) * metal : null-check ggml_metal_buffer_init result to avoid OOM crash ggml_backend_metal_buffer_type_alloc_buffer used the result of ggml_metal_buffer_init without checking for NULL. ggml_metal_buffer_init returns NULL when the underlying Metal allocation fails (e.g. an out-of-memory condition), and the following ggml_metal_buffer_is_shared(res) call dereferences it, turning a recoverable allocation failure into a hard crash (EXC_BAD_ACCESS). This is easy to hit on memory-constrained devices such as iOS when a model/context exceeds the available Metal budget. Log the failure using the existing GGML_LOG_ERROR convention and return NULL so the allocator surfaces a diagnosable error up the stack instead of crashing. * cont : fix log --------- Co-authored-by: Georgi Gerganov <ggerganov@gmail.com> </details> **Website:** - <https://llama.app> **Attestations:** - <https://github.com/ggml-org/llama.cpp/attestations/42843565> **macOS/iOS:** - [macOS Apple Silicon (arm64)](https://github.com/ggml-org/llama.cpp/releases/download/b10622/llama-b10622-bin-macos-arm64.tar.gz) - macOS Apple Silicon (arm64, KleidiAI enabled)',
    _learned_27322463c7e3,
)


def _learned_55ac9a819dc7(total: int, parts: int) -> tuple[int, ...]:
    """Split a non-negative tensor/work extent into balanced deterministic parts."""
    total_i = int(total)
    parts_i = int(parts)
    if total_i < 0 or parts_i < 1 or parts_i > 256:
        raise ValueError("tensor split inputs are out of bounds")
    base, extra = divmod(total_i, parts_i)
    return tuple(base + (1 if index < extra else 0) for index in range(parts_i))

register_capability(
    'balanced_tensor_split_55ac9a819dc7',
    "Split a bounded tensor/work extent deterministically across multiple execution parts. Verified lesson: Research-backed capability candidate from 'v0.3.0': ## Overview llama.cpp 0.3.0 introduces the dots3-note multimodal model (with a new DSA-ISWA KV cache), MTP support for GLM-4.5-Air, and tensor-split (`-sm tensor`) plus multi-sequence rollback fixes for DeepSeek 4. ggml is bumped to v0.22.0 (meta-backend tensor split, per-op Metal kernels with parallel compilation, non-in-place `ggml_clamp`), while mtmd gains dots3-note vision/audio, WebP decoding and a Pillow-accurate resize. The server adds a `LLAMA_SERVER_SLOTS_N_DIFF` debug knob, and the web UI gets tabbed chat navigation. ### New models",
    '## Overview llama.cpp 0.3.0 introduces the dots3-note multimodal model (with a new DSA-ISWA KV cache), MTP support for GLM-4.5-Air, and tensor-split (`-sm tensor`) plus multi-sequence rollback fixes for DeepSeek 4. ggml is bumped to v0.22.0 (meta-backend tensor split, per-op Metal kernels with parallel compilation, non-in-place `ggml_clamp`), while mtmd gains dots3-note vision/audio, WebP decoding and a Pillow-accurate resize. The server adds a `LLAMA_SERVER_SLOTS_N_DIFF` debug knob, and the web UI gets tabbed chat navigation. ### New models - Add dots3-note model with a new DSA-ISWA KV cache type ([#27060](https://github.com/ggml-org/llama.cpp/pull/27060)) ### Core changes - DeepSeek 4: add tensor-split mode via `-sm tensor` ([#26490](https://github.com/ggml-org/llama.cpp/pull/26490)) - DeepSeek 4: fix rollback with multiple sequences ([#26756](https://github.com/ggml-org/llama.cpp/pull/26756)) - Fix meta tensor split state propagation for tensor parallel ([#27574](https://github.com/ggml-org/llama.cpp/pull/27574)) - GLM-4.5-Air: add MTP (multi-token prediction) support ([#26534](https://github.com/ggml-org/llama.cpp/pull/26534)) - bailingmoe3: support DSpark ([#27508](https://git',
    _learned_55ac9a819dc7,
)


def _learned_1a50cc8a79a1(
    requested: str | None,
    available,
    fallback: str | None = None,
) -> str | None:
    """Prefer an explicit supported runtime device, then a compatible fallback."""
    choices = tuple(str(item).strip() for item in available if str(item).strip())
    preferred = str(requested).strip() if requested is not None else ""
    if preferred and preferred in choices:
        return preferred
    fallback_name = str(fallback).strip() if fallback is not None else ""
    if fallback_name and fallback_name in choices:
        return fallback_name
    return choices[0] if choices else None

register_capability(
    'runtime_device_selection_1a50cc8a79a1',
    "Select an explicit supported runtime device while preserving a compatible fallback path. Verified lesson: Research-backed capability candidate from 'b10643': <details open> hexagon: support for multi-NPU devices (IQ9, IQ10) and fully asynchronous backend (#26501) * hexagon: use non-host bufs by default and make the backend fully async * hex-hb: remove optional hostbuf support and fix async copy * hex-unary: relax supported unary check * hex-bufs: use same get_alignment for host bufs * snapdragon: bump android_platform to 34 * hex-rows: super hacky get/set rows for q8_0 * hex-get-rows: fix q8_0 * hex-get-rows: supprot for f16 and cleanup for q8_0 * hex-get-rows: generic macros and specialized threa",
    '<details open> hexagon: support for multi-NPU devices (IQ9, IQ10) and fully asynchronous backend (#26501) * hexagon: use non-host bufs by default and make the backend fully async * hex-hb: remove optional hostbuf support and fix async copy * hex-unary: relax supported unary check * hex-bufs: use same get_alignment for host bufs * snapdragon: bump android_platform to 34 * hex-rows: super hacky get/set rows for q8_0 * hex-get-rows: fix q8_0 * hex-get-rows: supprot for f16 and cleanup for q8_0 * hex-get-rows: generic macros and specialized thread funcs * hex-get-rows: add DMA pipeline, vtcm_layout and kernel params * hex-set-rows: fix q8_0 support, add dma and tracing * hex-tests: override nmse threshold for HTP of Q8_0 quants * hex-fa: add support for Q8_0 with inplace dequantizers * hex-get-rows: simplify type dispatch * hex-rows: simplify GET/SET_ROWS DMA pipeline * hex-async: add events, set/get-tensor-async and rest of the async api support * hex-repack: use slice instead of expert in repack functions * hex-cpy: update event/async-cpy logging * hex-set-rows: optimize smaller tensors * hex-geglu: fix perf regression with larger tensors * hex-get-rows: add missing header * hex-set-',
    _learned_1a50cc8a79a1,
)


def _learned_5e8c9057eb3e(items, limit: int = 32) -> tuple[str, ...]:
    """Return bounded caller values explicitly grounded in verified lesson terms."""
    limit_i = int(limit)
    if limit_i < 1 or limit_i > 128:
        raise ValueError("lesson-grounding limit is out of bounds")
    terms = ('bounded', 'this', 'lesson', 'research-backed', 'from', 'b10578', 'details', 'open', 'ggml', 'optimize', 'concat', 'replacing', 'per-element', 'memcpy', 'with', 'row-level')
    source = (items,) if isinstance(items, (str, bytes)) else items
    grounded: list[str] = []
    scanned = 0
    for item in source:
        scanned += 1
        if scanned > 256:
            break
        if isinstance(item, bytes):
            value = item.decode("utf-8", errors="replace").strip()
        else:
            value = str(item).strip()
        if not value:
            continue
        bounded = value[:512]
        lowered = bounded.lower()
        if any(term in lowered for term in terms):
            grounded.append(bounded)
        if len(grounded) >= limit_i:
            break
    return tuple(grounded)

register_capability(
    'learned_5e8c9057eb3eee81',
    "Ground bounded candidate context against terms derived only from the verified lesson/evidence before downstream use. Verified lesson: Add one new bounded Genesis capability implementing this verified transferable lesson: Research-backed capability candidate from 'b10578': <details open> ggml: optimize concat op by replacing per-element memcpy with row-level memcpy (#24575) * ggml: optimize concat op by replacing per-element memcpy with row-level memcpy * ggml: fix concat offsets for row-level copies * ggml: add concat row contiguity asserts * ggml: move concat block size asserts * ggml: remove redundant concat asserts * Update ggml/src/ggml-cpu/ops.cpp Co-authored-by: Sigbjørn Skjæret <sigbjorn.skjaeret@huggingface.co> ---",
    '<details open> ggml: optimize concat op by replacing per-element memcpy with row-level memcpy (#24575) * ggml: optimize concat op by replacing per-element memcpy with row-level memcpy * ggml: fix concat offsets for row-level copies * ggml: add concat row contiguity asserts * ggml: move concat block size asserts * ggml: remove redundant concat asserts * Update ggml/src/ggml-cpu/ops.cpp Co-authored-by: Sigbjørn Skjæret <sigbjorn.skjaeret@huggingface.co> --------- Co-authored-by: Sigbjørn Skjæret <sigbjorn.skjaeret@huggingface.co> </details> **Website:** - <https://llama.app> **Attestations:** - <https://github.com/ggml-org/llama.cpp/attestations/42306027> **macOS/iOS:** - [macOS Apple Silicon (arm64)](https://github.com/ggml-org/llama.cpp/releases/download/b10578/llama-b10578-bin-macos-arm64.tar.gz) - macOS Apple Silicon (arm64, KleidiAI enabled) [DISABLED](https://github.com/ggml-org/llama.cpp/pull/23780) - [macOS Intel (x64)](https://github.com/ggml-org/llama.cpp/releases/download/b10578/llama-b10578-bin-macos-x64.tar.gz) - [iOS XCFramework](https://github.com/ggml-org/llama.cpp/releases/download/b10578/llama-b10578-xcframework.zip) **Linux:** - [Ubuntu x64 (CPU)](https://github.co',
    _learned_5e8c9057eb3e,
)


def _learned_0a9a20044317(items, limit: int = 32) -> tuple[str, ...]:
    """Return bounded caller values explicitly grounded in verified lesson terms."""
    limit_i = int(limit)
    if limit_i < 1 or limit_i > 128:
        raise ValueError("lesson-grounding limit is out of bounds")
    terms = ('bounded', 'this', 'lesson', 'research-backed', 'from', 'b10582', 'details', 'open', 'restore', 'rocm', 'ubuntu', 'revert', 'disable', 'ubuntu-rocm', 'reverts', 'commit')
    source = (items,) if isinstance(items, (str, bytes)) else items
    grounded: list[str] = []
    scanned = 0
    for item in source:
        scanned += 1
        if scanned > 256:
            break
        if isinstance(item, bytes):
            value = item.decode("utf-8", errors="replace").strip()
        else:
            value = str(item).strip()
        if not value:
            continue
        bounded = value[:512]
        lowered = bounded.lower()
        if any(term in lowered for term in terms):
            grounded.append(bounded)
        if len(grounded) >= limit_i:
            break
    return tuple(grounded)

register_capability(
    'learned_0a9a20044317ace1',
    'Ground bounded candidate context against terms derived only from the verified lesson/evidence before downstream use. Verified lesson: Add one new bounded Genesis capability implementing this verified transferable lesson: Research-backed capability candidate from \'b10582\': <details open> ci : Restore ROCm job for Ubuntu (#27399) * Revert "ci : disable ubuntu-rocm (#26969)" This reverts commit 9558fa44c92746a58dd07ad1bf0c889715b938a6. * ci: set ccache compiler_check=content for ROCm build The ROCm toolchain is pip-installed fresh on every run, so the clang binary\'s mtime changes each time. With ccache\'s default compiler_check=mtime that invalidates the whole cache and warm builds only reached ~70% hits. Hash the compiler conte',
    '<details open> ci : Restore ROCm job for Ubuntu (#27399) * Revert "ci : disable ubuntu-rocm (#26969)" This reverts commit 9558fa44c92746a58dd07ad1bf0c889715b938a6. * ci: set ccache compiler_check=content for ROCm build The ROCm toolchain is pip-installed fresh on every run, so the clang binary\'s mtime changes each time. With ccache\'s default compiler_check=mtime that invalidates the whole cache and warm builds only reached ~70% hits. Hash the compiler contents instead so the cache survives toolchain reinstalls. * Update ccache size to 1GB We\'re waivering with so many architectures built, we need a bigger ccache limit. * merge fix --------- Co-authored-by: Jim Wu <ywu@xilinx.com> Co-authored-by: Sigbjørn Skjæret <sigbjorn.skjaeret@huggingface.co> </details> **Website:** - <https://llama.app> **Attestations:** - <https://github.com/ggml-org/llama.cpp/attestations/42320717> **macOS/iOS:** - [macOS Apple Silicon (arm64)](https://github.com/ggml-org/llama.cpp/releases/download/b10582/llama-b10582-bin-macos-arm64.tar.gz) - macOS Apple Silicon (arm64, KleidiAI enabled) [DISABLED](https://github.com/ggml-org/llama.cpp/pull/23780) - [macOS Intel (x64)](https://github.com/ggml-org/llama.cpp/',
    _learned_0a9a20044317,
)


def _learned_85ee71b19ede(
    artifact_name: str,
    available_artifacts,
    build_allowed: bool = True,
) -> tuple[str, bool]:
    """Reuse an already-built artifact and request a build only when it is missing."""
    artifact = str(artifact_name).strip()
    if not artifact:
        raise ValueError("artifact name is required")
    available: list[str] = []
    for item in available_artifacts:
        value = str(item).strip()
        if value and value not in available:
            available.append(value)
        if len(available) > 256:
            raise ValueError("available artifact set exceeds bounded size")
    if artifact in available:
        return artifact, False
    return artifact, bool(build_allowed)

register_capability(
    'reusable_build_artifact_85ee71b19ede',
    "Reuse an already-built/prebuilt artifact when available and request a build only when it is missing. Verified lesson: Add one new bounded Genesis capability implementing this verified transferable lesson: Research-backed capability candidate from 'b10636': <details open> ci: Clean up UI builds from releases (#27706) * ci : inline UI version resolution into ui-build.yml * ci : build UI once and reuse the artifact in release jobs Server jobs now extract the ui-build artifact into tools/ui/dist instead of npm-building the UI. Also removes the get-version job and the no-op -DHF_UI_VERSION flags. Assisted-by: pi:Kimi-K3 * ui : disable the npm UI build by default (LLAMA_BUILD_UI=OFF) The flag now only controls buil",
    '<details open> ci: Clean up UI builds from releases (#27706) * ci : inline UI version resolution into ui-build.yml * ci : build UI once and reuse the artifact in release jobs Server jobs now extract the ui-build artifact into tools/ui/dist instead of npm-building the UI. Also removes the get-version job and the no-op -DHF_UI_VERSION flags. Assisted-by: pi:Kimi-K3 * ui : disable the npm UI build by default (LLAMA_BUILD_UI=OFF) The flag now only controls building the UI from source via npm. The UI is still embedded by default from local tools/ui/dist or the prebuilt download (LLAMA_USE_PREBUILT_UI=ON). CI jobs no longer npm-build the UI; server-sanitize does not need node anymore. Assisted-by: pi:Kimi-K3 * ci : rename the ui-build artifact to llama-ui.zip Consistent with the other artifact names in the Actions summary. Assisted-by: pi:Kimi-K3 * ci : clarify the windows artifact merge in release.yml The windows-cuda/vulkan/sycl jobs build only the backend library; llama-server (with the embedded UI) is injected into their zips from the windows-cpu package during the release. State this in the job comments and use accurate wording in the merge step. Assisted-by: pi:Kimi-K3 </details>',
    _learned_85ee71b19ede,
)


def _learned_6d4702d4d1b9(items, limit: int = 32) -> tuple[str, ...]:
    """Return bounded caller values explicitly grounded in verified lesson terms."""
    limit_i = int(limit)
    if limit_i < 1 or limit_i > 128:
        raise ValueError("lesson-grounding limit is out of bounds")
    terms = ('bounded', 'this', 'lesson', 'research-backed', 'from', 'b10632', 'details', 'open', 'ggml-metal', 'chunked', 'mamba-2', 'prefill', 'optimization', 'metal', 'ssm_scan', 'kernels')
    source = (items,) if isinstance(items, (str, bytes)) else items
    grounded: list[str] = []
    scanned = 0
    for item in source:
        scanned += 1
        if scanned > 256:
            break
        if isinstance(item, bytes):
            value = item.decode("utf-8", errors="replace").strip()
        else:
            value = str(item).strip()
        if not value:
            continue
        bounded = value[:512]
        lowered = bounded.lower()
        if any(term in lowered for term in terms):
            grounded.append(bounded)
        if len(grounded) >= limit_i:
            break
    return tuple(grounded)

register_capability(
    'learned_6d4702d4d1b9e9b3',
    "Ground bounded candidate context against terms derived only from the verified lesson/evidence before downstream use. Verified lesson: Add one new bounded Genesis capability implementing this verified transferable lesson: Research-backed capability candidate from 'b10632': <details open> ggml-metal: add chunked SSD MMA for Mamba-2 prefill optimization (#26647) * metal: WIP chunked SSD SSM_SCAN kernels for multi-token prefill * metal: drop scalar SSD path; MMA + sequential tail * drop WIP ssm scan test noise * remove state_from_dst and rename CS and NSG constants * remove unrelated added whitespace padding * added clarity to mma_tokens calculation * added clarity to use_mma bool checks * added comments to metal ssd op constant",
    "<details open> ggml-metal: add chunked SSD MMA for Mamba-2 prefill optimization (#26647) * metal: WIP chunked SSD SSM_SCAN kernels for multi-token prefill * metal: drop scalar SSD path; MMA + sequential tail * drop WIP ssm scan test noise * remove state_from_dst and rename CS and NSG constants * remove unrelated added whitespace padding * added clarity to mma_tokens calculation * added clarity to use_mma bool checks * added comments to metal ssd op constants for clarity * reserve K tokens for sequential kernel rollback snapshots * reset concurrency between mma and seq tail * remove print args no longer used * fixed comment to no longer point to specific line * add FC_SSM_SCAN so seq path skips token offlset unless it's mma tail * added changes to new ssm.",
    _learned_6d4702d4d1b9,
)


def _learned_85587737002b(items, limit: int = 32) -> tuple[str, ...]:
    """Return bounded caller values explicitly grounded in verified lesson terms."""
    limit_i = int(limit)
    if limit_i < 1 or limit_i > 128:
        raise ValueError("lesson-grounding limit is out of bounds")
    terms = ('bounded', 'this', 'lesson', 'research-backed', 'from', 'v5.16.0', 'model', 'additions', 'qwen4-exp', 'width', 'height', 'image', 'https', 'github.com', 'user-attachments', 'assets')
    source = (items,) if isinstance(items, (str, bytes)) else items
    grounded: list[str] = []
    scanned = 0
    for item in source:
        scanned += 1
        if scanned > 256:
            break
        if isinstance(item, bytes):
            value = item.decode("utf-8", errors="replace").strip()
        else:
            value = str(item).strip()
        if not value:
            continue
        bounded = value[:512]
        lowered = bounded.lower()
        if any(term in lowered for term in terms):
            grounded.append(bounded)
        if len(grounded) >= limit_i:
            break
    return tuple(grounded)

register_capability(
    'learned_85587737002bedb8',
    'Ground bounded candidate context against terms derived only from the verified lesson/evidence before downstream use. Verified lesson: Add one new bounded Genesis capability implementing this verified transferable lesson: Research-backed capability candidate from \'Release: v5.16.0\': # Release v5.16.0 ## New Model additions ### Qwen4-Exp <img width="2241" height="693" alt="image" src="https://github.com/user-attachments/assets/c838b5ba-ffea-42da-baa9-3f66178e3671" /> Qwen4-Exp builds on Qwen3.5\'s hybrid text and multimodal architecture with three key components: GatedResidual (GR), Qwen Sparse Attention (QSA), and Per-Layer Embedding (PLE). GR is a Qwen-developed residual architecture that combines Hyper-Connection with GatedN',
    '# Release v5.16.0 ## New Model additions ### Qwen4-Exp <img width="2241" height="693" alt="image" src="https://github.com/user-attachments/assets/c838b5ba-ffea-42da-baa9-3f66178e3671" /> Qwen4-Exp builds on Qwen3.5\'s hybrid text and multimodal architecture with three key components: GatedResidual (GR), Qwen Sparse Attention (QSA), and Per-Layer Embedding (PLE). GR is a Qwen-developed residual architecture that combines Hyper-Connection with GatedNorm. It mixes multiple residual streams with fine-grained elementwise gating before each attention and Mixture-of-Experts (MoE) block, then controls how much of the block output is injected back into each stream. QSA uses multiple query heads to score compressed key blocks, selects the most relevant contiguous token blocks, and keeps the incomplete trailing block uncompressed. This block-level selection reduces indexing overhead and improves memory locality for long sequences. Combined with Gated DeltaNet, QSA makes Qwen4-Exp the first hybrid architecture to integrate linear and sparse attention, substantially improving inference efficiency for long-context workloads. PLE enriches selected decoder layers with layer-specific lexical feature',
    _learned_85587737002b,
)


def _learned_9d26bc0034d1(items, limit: int = 32) -> tuple[str, ...]:
    """Return bounded caller values explicitly grounded in verified lesson terms."""
    limit_i = int(limit)
    if limit_i < 1 or limit_i > 128:
        raise ValueError("lesson-grounding limit is out of bounds")
    terms = ('bounded', 'this', 'lesson', 'research-backed', 'from', 'bellman', 'calibration', 'marginalized', 'importance', 'weighting', 'offline', 'reinforcement', 'evaluates', 'target', 'policy', 'reweighting')
    source = (items,) if isinstance(items, (str, bytes)) else items
    grounded: list[str] = []
    scanned = 0
    for item in source:
        scanned += 1
        if scanned > 256:
            break
        if isinstance(item, bytes):
            value = item.decode("utf-8", errors="replace").strip()
        else:
            value = str(item).strip()
        if not value:
            continue
        bounded = value[:512]
        lowered = bounded.lower()
        if any(term in lowered for term in terms):
            grounded.append(bounded)
        if len(grounded) >= limit_i:
            break
    return tuple(grounded)

register_capability(
    'learned_9d26bc0034d19aa8',
    "Ground bounded candidate context against terms derived only from the verified lesson/evidence before downstream use. Verified lesson: Add one new bounded Genesis capability implementing this verified transferable lesson: Research-backed capability candidate from 'Bellman Calibration for Marginalized Importance Weighting in Offline Reinforcement Learning': Marginalized importance weighting evaluates a target policy by reweighting offline state-action samples with its discounted occupancy ratio, characterized by an adjoint Bellman equation. Existing minimax, primal-dual, and fitted fixed-point estimators can leave residual occupancy-balance violations because of function-class approximation, regularization, or incomplete optim",
    "Marginalized importance weighting evaluates a target policy by reweighting offline state-action samples with its discounted occupancy ratio, characterized by an adjoint Bellman equation. Existing minimax, primal-dual, and fitted fixed-point estimators can leave residual occupancy-balance violations because of function-class approximation, regularization, or incomplete optimization. These violations are difficult to diagnose and reduce because the objectives generally lack a direct supervised validation loss for hyperparameter tuning, model selection, and early stopping. We introduce isotonic Bellman calibration, a one-dimensional, model-agnostic post-processing method that reduces these violations while preserving the ranking information in any initial occupancy-ratio estimate. The method corrects the estimate's scale and shape by applying fitted occupancy-ratio evaluation (FORE) over a one-dimensional class of nondecreasing transformations. We characterize Bellman calibration as a conditional fixed-point property equivalent to occupancy-balance against every test function of the calibrated ratio. More generally, we derive a calibration-refinement bound showing that any fitted rati",
    _learned_9d26bc0034d1,
)


def _learned_98c905dd9dff(items, limit: int = 32) -> tuple[str, ...]:
    """Return bounded caller values explicitly grounded in verified lesson terms."""
    limit_i = int(limit)
    if limit_i < 1 or limit_i > 128:
        raise ValueError("lesson-grounding limit is out of bounds")
    terms = ('bounded', 'this', 'lesson', 'research-backed', 'from', 'improving', 'cross-problem', 'vehicle', 'routing', 'with', 'locally', 'augmented', 'preferences', 'representation', 'disentanglement', 'multi-task')
    source = (items,) if isinstance(items, (str, bytes)) else items
    grounded: list[str] = []
    scanned = 0
    for item in source:
        scanned += 1
        if scanned > 256:
            break
        if isinstance(item, bytes):
            value = item.decode("utf-8", errors="replace").strip()
        else:
            value = str(item).strip()
        if not value:
            continue
        bounded = value[:512]
        lowered = bounded.lower()
        if any(term in lowered for term in terms):
            grounded.append(bounded)
        if len(grounded) >= limit_i:
            break
    return tuple(grounded)

register_capability(
    'learned_98c905dd9dff5c19',
    "Ground bounded candidate context against terms derived only from the verified lesson/evidence before downstream use. Verified lesson: Add one new bounded Genesis capability implementing this verified transferable lesson: Research-backed capability candidate from 'Improving Cross-Problem Vehicle Routing with Locally Augmented Preferences and Representation Disentanglement': Multi-task vehicle routing problem (VRP) solvers seek to handle multiple VRP variants within a single unified model, avoiding the need to train a separate model for every variant. In spite of recent progress, current approaches remain limited on two fronts. On the training side, reinforcement learning suffers from reward-scale disparities and shrinking adv",
    "Multi-task vehicle routing problem (VRP) solvers seek to handle multiple VRP variants within a single unified model, avoiding the need to train a separate model for every variant. In spite of recent progress, current approaches remain limited on two fronts. On the training side, reinforcement learning suffers from reward-scale disparities and shrinking advantage signals as policies improve, whereas preference optimization stagnates once sampled tours become near-identical and thus fundamentally limited by the quality of the policy's own generated solutions, leaving both paradigms with weak supervision as training progresses. On the architecture side, existing fully shared encoders entangle constraint-dependent representations across heterogeneous variants, which limits generalization. We address these gaps with two model-agnostic contributions. First, we propose Preference Optimization with Locally Augmented Refinement (POLAR), a novel training algorithm that applies a local search refinement pass to the best decoded tour before forming preference pairs, yielding much more informative pairwise margins. Second, a Progressive Layered Extraction (PLE) encoder routes each encoder layer",
    _learned_98c905dd9dff,
)


def _learned_cda77e4603bf(items, limit: int = 32) -> tuple[str, ...]:
    """Return bounded caller values explicitly grounded in verified lesson terms."""
    limit_i = int(limit)
    if limit_i < 1 or limit_i > 128:
        raise ValueError("lesson-grounding limit is out of bounds")
    terms = ('bounded', 'this', 'lesson', 'research-backed', 'from', 'patch', 'v5.14.1', 'solves', 'issues', 'which', 'appeared', 'when', 'integrating', 'inkling', 'model', 'most')
    source = (items,) if isinstance(items, (str, bytes)) else items
    grounded: list[str] = []
    scanned = 0
    for item in source:
        scanned += 1
        if scanned > 256:
            break
        if isinstance(item, bytes):
            value = item.decode("utf-8", errors="replace").strip()
        else:
            value = str(item).strip()
        if not value:
            continue
        bounded = value[:512]
        lowered = bounded.lower()
        if any(term in lowered for term in terms):
            grounded.append(bounded)
        if len(grounded) >= limit_i:
            break
    return tuple(grounded)

register_capability(
    'learned_cda77e4603bfc6d2',
    "Ground bounded candidate context against terms derived only from the verified lesson/evidence before downstream use. Verified lesson: Add one new bounded Genesis capability implementing this verified transferable lesson: Research-backed capability candidate from 'Patch release: v5.14.1': # Patch release v5.14.1 This patch solves a few issues which appeared when integrating Inkling model, most notably an issue affecting models using EncoderDecoderCache during assisted generation. It also fixes an issue that could appear during prefill with StaticCache and sdpa without padding for Inkling which uses a position_bias. It contains the following commits: - Fix sdpa prefill with position_bias (#47359) by @Cyrilvallez - Fix assisted",
    '# Patch release v5.14.1 This patch solves a few issues which appeared when integrating Inkling model, most notably an issue affecting models using EncoderDecoderCache during assisted generation. It also fixes an issue that could appear during prefill with StaticCache and sdpa without padding for Inkling which uses a position_bias. It contains the following commits: - Fix sdpa prefill with position_bias (#47359) by @Cyrilvallez - Fix assisted decoding for models with EncoderDecoder cache & OlmoHybrid (#47361) by @Cyrilvallez - [FP8] Bump kernels version (#47344) by @vasqu - Fix deepgemm on multiple devices (#47323) by @IlyasMoutawwakil',
    _learned_cda77e4603bf,
)


def _learned_872ec47e54e2(items, limit: int = 32) -> tuple[str, ...]:
    """Return bounded caller values explicitly grounded in verified lesson terms."""
    limit_i = int(limit)
    if limit_i < 1 or limit_i > 128:
        raise ValueError("lesson-grounding limit is out of bounds")
    terms = ('bounded', 'this', 'lesson', 'research-backed', 'from', 'b10593', 'details', 'open', 'deepseekv4', 'rollback', 'with', 'multi-seq', 'model', 'loading', 'make', 'pending')
    source = (items,) if isinstance(items, (str, bytes)) else items
    grounded: list[str] = []
    scanned = 0
    for item in source:
        scanned += 1
        if scanned > 256:
            break
        if isinstance(item, bytes):
            value = item.decode("utf-8", errors="replace").strip()
        else:
            value = str(item).strip()
        if not value:
            continue
        bounded = value[:512]
        lowered = bounded.lower()
        if any(term in lowered for term in terms):
            grounded.append(bounded)
        if len(grounded) >= limit_i:
            break
    return tuple(grounded)

register_capability(
    'learned_872ec47e54e29dcd',
    "Ground bounded candidate context against terms derived only from the verified lesson/evidence before downstream use. Verified lesson: Add one new bounded Genesis capability implementing this verified transferable lesson: Research-backed capability candidate from 'b10593': <details open> DeepseekV4: fix rollback with multi-seq (#26756) * DeepseekV4: fix rollback with multi-seq * fix model loading * make pending rollback single use * only clear cache for seq_id for full load * add assert for compress ratio * make graph topology static * pass true instead of flags in clear_compressed * cont : clean-up + TODOs --------- Co-authored-by: Georgi Gerganov <ggerganov@gmail.com> </details> **Website:** - <https://llama.app> **Attestat",
    '<details open> DeepseekV4: fix rollback with multi-seq (#26756) * DeepseekV4: fix rollback with multi-seq * fix model loading * make pending rollback single use * only clear cache for seq_id for full load * add assert for compress ratio * make graph topology static * pass true instead of flags in clear_compressed * cont : clean-up + TODOs --------- Co-authored-by: Georgi Gerganov <ggerganov@gmail.com> </details> **Website:** - <https://llama.app> **Attestations:** - <https://github.com/ggml-org/llama.cpp/attestations/42415702> **macOS/iOS:** - [macOS Apple Silicon (arm64)](https://github.com/ggml-org/llama.cpp/releases/download/b10593/llama-b10593-bin-macos-arm64.tar.gz) - macOS Apple Silicon (arm64, KleidiAI enabled) [DISABLED](https://github.com/ggml-org/llama.cpp/pull/23780) - [macOS Intel (x64)](https://github.com/ggml-org/llama.cpp/releases/download/b10593/llama-b10593-bin-macos-x64.tar.gz) - [iOS XCFramework](https://github.com/ggml-org/llama.cpp/releases/download/b10593/llama-b10593-xcframework.zip) **Linux:** - [Ubuntu x64 (CPU)](https://github.com/ggml-org/llama.cpp/releases/download/b10593/llama-b10593-bin-ubuntu-x64.tar.gz) - [Ubuntu arm64 (CPU)](https://github.com/ggml-',
    _learned_872ec47e54e2,
)


def _learned_288188cc73f3(steps, limit: int = 32) -> tuple[str, ...]:
    """Normalize a bounded ordered tool workflow for later verified execution."""
    limit_i = int(limit)
    if limit_i < 1 or limit_i > 128:
        raise ValueError("tool workflow limit is out of bounds")
    normalized: list[str] = []
    for step in steps:
        value = str(step).strip()
        if value and value not in normalized:
            normalized.append(value)
        if len(normalized) >= limit_i:
            break
    return tuple(normalized)

register_capability(
    'bounded_tool_workflow_288188cc73f3',
    "Normalize a bounded ordered tool workflow while preserving explicit tool-step intent. Verified lesson: Add one new bounded Genesis capability implementing this verified transferable lesson: Research-backed capability candidate from 'MidTool: Mid-training Data Synthesis for Agentic Tool Use': Mid-training is increasingly recognized as a critical stage for shaping the capabilities of large language models. Recent work has shown that targeted mid-training can strengthen reasoning-intensive abilities such as math and science, and can also improve agentic capabilities in software-engineering settings. In this work, we study the parallel but less explored agentic capability: general tool use. We pres",
    'Mid-training is increasingly recognized as a critical stage for shaping the capabilities of large language models. Recent work has shown that targeted mid-training can strengthen reasoning-intensive abilities such as math and science, and can also improve agentic capabilities in software-engineering settings. In this work, we study the parallel but less explored agentic capability: general tool use. We present MidTool, an open corpus construction pipeline for agentic tool-use mid-training that combines large-scale web, PDF, and code data with synthesized supervision from real-world tool APIs, MCP skills, and document-grounded workflows. MidTool is designed to teach models how to recognize tool affordances, ground arguments from context, compose tool call workflow, and recover from incomplete information. We mid-train Qwen3-4B-Base and Qwen3-8B-Base on MidTool-Mix, and then apply follow-up post-training with both supervised fine-tuning and reinforcement learning. Compared with baselines, MidTool-Mix consistently improves downstream performance under both SFT and RL on BFCL, tau2-Bench, and MCP Universe. These results suggest that general tool use, like other important LLM capabiliti',
    _learned_288188cc73f3,
)


# GENESIS_LEARNED_CAPABILITY_INSERTION_POINT
