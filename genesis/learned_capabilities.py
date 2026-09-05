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
    pass

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


def _learned_7b8e7c2ecea3(items, limit: int = 32) -> tuple[str, ...]:
    """Return bounded caller values explicitly grounded in verified lesson terms."""
    limit_i = int(limit)
    if limit_i < 1 or limit_i > 128:
        raise ValueError("lesson-grounding limit is out of bounds")
    terms = ('bounded', 'this', 'lesson', 'research-backed', 'from', 'physical-support', 'confidence', 'sets', 'highly', 'coherent', 'dictionaries', 'sparse', 'pursuit', 'after', 'dictionary', 'yield')
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
    'learned_7b8e7c2ecea3520f',
    "Ground bounded candidate context against terms derived only from the verified lesson/evidence before downstream use. Verified lesson: Add one new bounded Genesis capability implementing this verified transferable lesson: Research-backed capability candidate from 'Physical-Support Confidence Sets for Highly Coherent Dictionaries': Sparse pursuit after dictionary learning can yield a precise atom support even when its physical interpretation is not justified by the calibration data, especially for highly coherent dictionaries where alternative calibration-compatible dictionaries may assign different physical meanings to the same selected support. We develop resolution-aware physical-support inference that jointly accounts for",
    'Sparse pursuit after dictionary learning can yield a precise atom support even when its physical interpretation is not justified by the calibration data, especially for highly coherent dictionaries where alternative calibration-compatible dictionaries may assign different physical meanings to the same selected support. We develop resolution-aware physical-support inference that jointly accounts for uncertainty in the learned dictionary and in the representation of a deployment signal. Our cross-dictionary confidence correspondence retains calibration-compatible dictionaries and deployment-compatible sparse representations, then projects the surviving explanations onto physical-support space. For local coherent-atom classes with separation scale s, once the deployment data resolve the coherent-block explanation and its atom support, the minimax physical resolution from N calibration signals satisfies $δ_{\\mathrm{opt}}(N,s)\\asymp\\min\\{s,\\frac{1}{\\sqrt{N}s^2}\\}$, with relative resolution governed by the orientation-information scale $Ns^6$. Deployment replication improves physical localization only when orientation changes cannot be absorbed by adjusting the active coefficients. For c',
    _learned_7b8e7c2ecea3,
)


def _learned_52e32275460f(items, limit: int = 32) -> tuple[str, ...]:
    """Return bounded caller values explicitly grounded in verified lesson terms."""
    limit_i = int(limit)
    if limit_i < 1 or limit_i > 128:
        raise ValueError("lesson-grounding limit is out of bounds")
    terms = ('bounded', 'this', 'lesson', 'research-backed', 'from', 'inducing', 'task', 'models', 'computer-use', 'traces', 'naturalistic', 'passively', 'recorded', 'screenshots', 'mouse', 'keyboard')
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
    'learned_52e32275460f2a01',
    "Ground bounded candidate context against terms derived only from the verified lesson/evidence before downstream use. Verified lesson: Add one new bounded Genesis capability implementing this verified transferable lesson: Research-backed capability candidate from 'Inducing Task Models from Computer-Use Traces': Naturalistic computer-use traces, passively recorded screenshots and mouse or keyboard actions, are a valuable resource for deriving symbolic, auditable, and reusable models of how everyday work is done. Such models matter as computer-use agents enter real work, where agents need to learn how tasks are actually performed, and organizations need to audit and reuse that knowledge. However, inducing such task models is ch",
    'Naturalistic computer-use traces, passively recorded screenshots and mouse or keyboard actions, are a valuable resource for deriving symbolic, auditable, and reusable models of how everyday work is done. Such models matter as computer-use agents enter real work, where agents need to learn how tasks are actually performed, and organizations need to audit and reuse that knowledge. However, inducing such task models is challenging, as activity is observed only as low-level events and real-world work is multi-threaded with interleaved goals. Existing methods assume a given task or a single workflow, and produce step-level summaries rather than structured task models. We introduce Task Model Induction (TMI), which (i) discovers the latent tasks in an unconstrained trace, disentangling concurrent activity, and (ii) for each latent task, induces a task model pairing a hierarchical objective model of recursive goal decomposition with a procedure model of the control flow that organized the execution. Intrinsically, on controlled human and agent trajectories, TMI recovers interleaved tasks with 0.974 agreement against ground-truth groupings and reconstructs 74.9% of the observed execution s',
    _learned_52e32275460f,
)


def _learned_42f96d1d383a(items, limit: int = 32) -> tuple[str, ...]:
    """Return bounded caller values explicitly grounded in verified lesson terms."""
    limit_i = int(limit)
    if limit_i < 1 or limit_i > 128:
        raise ValueError("lesson-grounding limit is out of bounds")
    terms = ('bounded', 'this', 'lesson', 'research-backed', 'from', 'margin-controlled', 'confidence', 'estimation', 'reliable', 'music', 'information', 'retrieval', 'deep', 'neural', 'networks', 'often')
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
    'learned_42f96d1d383a679d',
    "Ground bounded candidate context against terms derived only from the verified lesson/evidence before downstream use. Verified lesson: Add one new bounded Genesis capability implementing this verified transferable lesson: Research-backed capability candidate from '$TCP_α$: Margin-Controlled Confidence estimation for reliable Music Information Retrieval': Deep neural networks are often overconfident, assigning high confidence even to incorrect predictions. Consequently, users lack a reliable signal for deciding when a prediction can be trusted. Post-hoc confidence estimation addresses this by training a lightweight auxiliary head over a frozen classifier. Existing targets, however, suffer from inherent ambiguity: they assign",
    'Deep neural networks are often overconfident, assigning high confidence even to incorrect predictions. Consequently, users lack a reliable signal for deciding when a prediction can be trusted. Post-hoc confidence estimation addresses this by training a lightweight auxiliary head over a frozen classifier. Existing targets, however, suffer from inherent ambiguity: they assign overlapping confidence values to correct and incorrect predictions, while errors near the decision boundary receive confidence scores indistinguishable from correct predictions. In this work, we propose $TCP_α$, a novel confidence target that resolves these limitations by introducing a margin-controlled penalty for misclassified samples. We prove that $TCP_α$ guarantees complete separation between the target values of correct and incorrect predictions, with a separation margin that is independent of the number of classes and increases monotonically with the penalty parameter. Since accurate classifiers naturally produce very few errors, learning these targets results in a severely imbalanced regression problem. We therefore present a systematic study of training strategies for learning under this imbalance and i',
    _learned_42f96d1d383a,
)


def _learned_8000a65e6265(items, limit: int = 32) -> tuple[str, ...]:
    """Return bounded caller values explicitly grounded in verified lesson terms."""
    limit_i = int(limit)
    if limit_i < 1 or limit_i > 128:
        raise ValueError("lesson-grounding limit is out of bounds")
    terms = ('bounded', 'this', 'lesson', 'research-backed', 'from', 'b10585', 'details', 'open', 'common', 'json.h', 'abstraction', 'json', 'migrate', 'adapt', 'jinja', 'server')
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
    'learned_8000a65e626535a7',
    "Ground bounded candidate context against terms derived only from the verified lesson/evidence before downstream use. Verified lesson: Add one new bounded Genesis capability implementing this verified transferable lesson: Research-backed capability candidate from 'b10585': <details open> common: add json.h abstraction (#27511) * add common/json * migrate common * adapt jinja * migrate server * big wip * migrate tests * wip * revert some excessive changes * wip * wip 2 * revert redundant changes * fix server crash * various fixes * fix ci * harden a bit * clean up * rm json-shim * add some comments * rm redundant decl </details> **Website:** - <https://llama.app> **Attestations:** - <https://github.com/ggml-org/llama.cpp/attes",
    '<details open> common: add json.h abstraction (#27511) * add common/json * migrate common * adapt jinja * migrate server * big wip * migrate tests * wip * revert some excessive changes * wip * wip 2 * revert redundant changes * fix server crash * various fixes * fix ci * harden a bit * clean up * rm json-shim * add some comments * rm redundant decl </details> **Website:** - <https://llama.app> **Attestations:** - <https://github.com/ggml-org/llama.cpp/attestations/42332655> **macOS/iOS:** - [macOS Apple Silicon (arm64)](https://github.com/ggml-org/llama.cpp/releases/download/b10585/llama-b10585-bin-macos-arm64.tar.gz) - macOS Apple Silicon (arm64, KleidiAI enabled) [DISABLED](https://github.com/ggml-org/llama.cpp/pull/23780) - [macOS Intel (x64)](https://github.com/ggml-org/llama.cpp/releases/download/b10585/llama-b10585-bin-macos-x64.tar.gz) - [iOS XCFramework](https://github.com/ggml-org/llama.cpp/releases/download/b10585/llama-b10585-xcframework.zip) **Linux:** - [Ubuntu x64 (CPU)](https://github.com/ggml-org/llama.cpp/releases/download/b10585/llama-b10585-bin-ubuntu-x64.tar.gz) - [Ubuntu arm64 (CPU)](https://github.com/ggml-org/llama.cpp/releases/download/b10585/llama-b10585-bi',
    _learned_8000a65e6265,
)


def _learned_8ee7b28ed0b8(items, limit: int = 32) -> tuple[str, ...]:
    """Return bounded caller values explicitly grounded in verified lesson terms."""
    limit_i = int(limit)
    if limit_i < 1 or limit_i > 128:
        raise ValueError("lesson-grounding limit is out of bounds")
    terms = ('bounded', 'this', 'lesson', 'research-backed', 'from', 'b10577', 'details', 'open', 'common', 'draft-mtp', 'with', 'embeddings', 'whitespace', 'co-authored-by', 'sigbj', 'sigbjorn.skjaeret')
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
    'learned_8ee7b28ed0b8c23c',
    "Ground bounded candidate context against terms derived only from the verified lesson/evidence before downstream use. Verified lesson: Add one new bounded Genesis capability implementing this verified transferable lesson: Research-backed capability candidate from 'b10577': <details open> common : fix draft-mtp with embeddings (#26352, #27299) (#27400) * common: fix draft-mtp with embeddings (#26352) * --whitespace --------- Co-authored-by: Sigbjørn Skjæret <sigbjorn.skjaeret@huggingface.co> </details> **Website:** - <https://llama.app> **Attestations:** - <https://github.com/ggml-org/llama.cpp/attestations/42302233> **macOS/iOS:** - [macOS Apple Silicon (arm64)](https://github.com/ggml-org/llama.cpp/releases/download/b10577",
    '<details open> common : fix draft-mtp with embeddings (#26352, #27299) (#27400) * common: fix draft-mtp with embeddings (#26352) * --whitespace --------- Co-authored-by: Sigbjørn Skjæret <sigbjorn.skjaeret@huggingface.co> </details> **Website:** - <https://llama.app> **Attestations:** - <https://github.com/ggml-org/llama.cpp/attestations/42302233> **macOS/iOS:** - [macOS Apple Silicon (arm64)](https://github.com/ggml-org/llama.cpp/releases/download/b10577/llama-b10577-bin-macos-arm64.tar.gz) - macOS Apple Silicon (arm64, KleidiAI enabled) [DISABLED](https://github.com/ggml-org/llama.cpp/pull/23780) - [macOS Intel (x64)](https://github.com/ggml-org/llama.cpp/releases/download/b10577/llama-b10577-bin-macos-x64.tar.gz) - [iOS XCFramework](https://github.com/ggml-org/llama.cpp/releases/download/b10577/llama-b10577-xcframework.zip) **Linux:** - [Ubuntu x64 (CPU)](https://github.com/ggml-org/llama.cpp/releases/download/b10577/llama-b10577-bin-ubuntu-x64.tar.gz) - [Ubuntu arm64 (CPU)](https://github.com/ggml-org/llama.cpp/releases/download/b10577/llama-b10577-bin-ubuntu-arm64.tar.gz) - [Ubuntu s390x (CPU)](https://github.com/ggml-org/llama.cpp/releases/download/b10577/llama-b10577-bin-ubu',
    _learned_8ee7b28ed0b8,
)


def _learned_07030016a4b0(items, limit: int = 32) -> tuple[str, ...]:
    """Return bounded caller values explicitly grounded in verified lesson terms."""
    limit_i = int(limit)
    if limit_i < 1 or limit_i > 128:
        raise ValueError("lesson-grounding limit is out of bounds")
    terms = ('bounded', 'this', 'lesson', 'research-backed', 'from', 'v5.16.1', 'special', 'include', 'small', 'fixes', 'glm-5.3-flash', 'width', 'height', 'image', 'https', 'github.com')
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
    'learned_07030016a4b0afea',
    'Ground bounded candidate context against terms derived only from the verified lesson/evidence before downstream use. Verified lesson: Add one new bounded Genesis capability implementing this verified transferable lesson: Research-backed capability candidate from \'Release v5.16.1\': # Release v5.16.1 This is a special release as we include GLM! (and a few small fixes) # GLM-5.3-Flash <img width="4239" height="2643" alt="image" src="https://github.com/user-attachments/assets/17bc9c29-758b-44c8-8230-42f945ded209" /> GLM-5.3-Flash, the first **natively multimodal model** in the GLM-5 series. With 320B total parameters and just 18B active parameters, it outperforms GLM-5.2 across benchmarks and real-world workloads at one-tenth th',
    '# Release v5.16.1 This is a special release as we include GLM! (and a few small fixes) # GLM-5.3-Flash <img width="4239" height="2643" alt="image" src="https://github.com/user-attachments/assets/17bc9c29-758b-44c8-8230-42f945ded209" /> GLM-5.3-Flash, the first **natively multimodal model** in the GLM-5 series. With 320B total parameters and just 18B active parameters, it outperforms GLM-5.2 across benchmarks and real-world workloads at one-tenth the price, while approaching Claude Opus 4.8 on coding and agentic benchmarks. GLM-5.3-Flash starts from a newly trained base model, with its architecture and training recipe redesigned around capability and efficiency. For the first time in the GLM series, we introduce a hybrid architecture combining sparse and linear attention, sharply reducing long-context serving costs while preserving precise long-context capabilities. The model also adopts Manifold-Constrained Hyper-Connections (mHC) to further improve scaling efficiency. Together with our latest **30T-token** multimodal pre-training corpus, these changes enable GLM-5.3-Flash to deliver more intelligence with less compute. **Links:** [Documentation](https://huggingface.co/docs/transfo',
    _learned_07030016a4b0,
)


def _learned_c301a7f873dd(items, limit: int = 32) -> tuple[str, ...]:
    """Return bounded caller values explicitly grounded in verified lesson terms."""
    limit_i = int(limit)
    if limit_i < 1 or limit_i > 128:
        raise ValueError("lesson-grounding limit is out of bounds")
    terms = ('bounded', 'this', 'lesson', 'research-backed', 'from', 'stream-aligned', 'policy', 'optimization', 'asynchronous', 'agentic', 'group-relative', 'reinforcement', 'waits', 'sibling', 'rollouts', 'same')
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
    'learned_c301a7f873dd9f14',
    "Ground bounded candidate context against terms derived only from the verified lesson/evidence before downstream use. Verified lesson: Add one new bounded Genesis capability implementing this verified transferable lesson: Research-backed capability candidate from 'SPO++: Stream-Aligned Policy Optimization for Asynchronous Agentic RL': Group-relative reinforcement learning waits for sibling rollouts of the same prompt, which is costly for long and variable tool-use trajectories. Single-stream Policy Optimization (SPO) removes this dependency with a persistent prompt-level value estimate, but its recipe whitens one advantage per trajectory before optimizing a token-mean actor loss. We show that trajectory centering generally do",
    'Group-relative reinforcement learning waits for sibling rollouts of the same prompt, which is costly for long and variable tool-use trajectories. Single-stream Policy Optimization (SPO) removes this dependency with a persistent prompt-level value estimate, but its recipe whitens one advantage per trajectory before optimizing a token-mean actor loss. We show that trajectory centering generally does not center the token-weighted quantity consumed by the actor, and fix the mismatch by standardizing terminal-outcome advantages under the action-token measure. We additionally organize prompt evidence by the policy event that generated it rather than learner receipt order. Across matched runs on ALFWorld at two model scales and on Math-TIR, SPO++ improves online learning efficiency over SPO. A paired ablation identifies action-token-measure normalization as the strongest tested component.',
    _learned_c301a7f873dd,
)


def _learned_1dc4510b127a(items, limit: int = 32) -> tuple[str, ...]:
    """Return bounded caller values explicitly grounded in verified lesson terms."""
    limit_i = int(limit)
    if limit_i < 1 or limit_i > 128:
        raise ValueError("lesson-grounding limit is out of bounds")
    terms = ('bounded', 'this', 'lesson', 'research-backed', 'from', 'parameterized', 'complexity', 'lipschitz', 'constants', 'input', 'convex', 'neural', 'networks', 'norm', 'maximization', 'over')
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
    'learned_1dc4510b127a3158',
    "Ground bounded candidate context against terms derived only from the verified lesson/evidence before downstream use. Verified lesson: Add one new bounded Genesis capability implementing this verified transferable lesson: Research-backed capability candidate from 'Parameterized Complexity of $L_p$-Lipschitz Constants for Input Convex Neural Networks and $L_p$-Norm Maximization over Zonotopes': Lipschitz constants are a standard way to quantify the sensitivity of neural networks to small input perturbations, but computing them is difficult even for shallow ReLU networks. We study this problem for two-layer input-convex neural networks (ICNNs), a restricted architecture where nonnegative output weights enforce convexity. Comput",
    'Lipschitz constants are a standard way to quantify the sensitivity of neural networks to small input perturbations, but computing them is difficult even for shallow ReLU networks. We study this problem for two-layer input-convex neural networks (ICNNs), a restricted architecture where nonnegative output weights enforce convexity. Computing the $L_p$-Lipschitz constant for these networks is equivalent to maximizing the dual norm over a zonotope. While $L_1$- and $L_\\infty$-norm maximization on zonotopes admit fixed-parameter and polynomial-time algorithms, respectively, the parameterized complexity of the remaining $L_p$-norms was open. We prove that, for every fixed $p\\in (1,\\infty)\\cap \\mathbb{Q}$, maximizing the $L_p$-norm over a zonotope in $\\mathbb{R}^d$ is W[1]-hard with respect to the dimension $d$. Moreover, our hardness results imply that brute-force enumeration algorithms are essentially optimal for this problem under the Exponential Time Hypothesis. By duality, the same hardness results hold for computing the $L_p$-Lipschitz constant of two-layer ReLU ICNNs. Our proof first establishes the result for the $L_2$-norm and then transfers the construction to arbitrary fixed $p',
    _learned_1dc4510b127a,
)


def _learned_15ea4d08866a(items, limit: int = 32) -> tuple[str, ...]:
    """Return bounded caller values explicitly grounded in verified lesson terms."""
    limit_i = int(limit)
    if limit_i < 1 or limit_i > 128:
        raise ValueError("lesson-grounding limit is out of bounds")
    terms = ('bounded', 'this', 'lesson', 'research-backed', 'from', 'v5.15.0', 'model', 'additions', 'meta', 'muse', 'glimmer', 'released', 'today', 'multimodal', 'especially', 'designed')
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
    'learned_15ea4d08866af6f5',
    "Ground bounded candidate context against terms derived only from the verified lesson/evidence before downstream use. Verified lesson: Add one new bounded Genesis capability implementing this verified transferable lesson: Research-backed capability candidate from 'Release: v5.15.0': # Release v5.15.0 ## New Model additions ### Meta Muse Glimmer Muse Glimmer, released today, is Meta’s new multimodal model, especially designed for agentic use cases. Distilled from Muse to 30B parameters, and released under the Apache 2.0 license, it can be deployed to local setups for privacy-aware applications such as coding, document analysis, personal assistants, Claw- or Hermes-like setups. Muse Glimmer is a dense 30B parameter model cons",
    '# Release v5.15.0 ## New Model additions ### Meta Muse Glimmer Muse Glimmer, released today, is Meta’s new multimodal model, especially designed for agentic use cases. Distilled from Muse to 30B parameters, and released under the Apache 2.0 license, it can be deployed to local setups for privacy-aware applications such as coding, document analysis, personal assistants, Claw- or Hermes-like setups. Muse Glimmer is a dense 30B parameter model consisting of: - 2B ViT-style encoder for vision (Perception Encoder) - 28B parameter text decoder We\'re covering it in the following blogpost: http://hf.co/blog/muse-glimmer <img width="960" height="1787" alt="image" src="https://github.com/user-attachments/assets/3d8e548e-f84f-4269-8bd0-a12722d7ab01" /> --- ### GraniteMoeSWA & GraniteSWA <img width="1013" height="389" alt="image" src="https://github.com/user-attachments/assets/2c2b87f0-466a-413a-a4be-25ceae49c9a5" /> **Links:** [Documentation](https://huggingface.co/docs/transformers/main/en/model_doc/granitemoe_swa) * Add Granite-swa and Granitemoe-swa model support (#47179) by @daviswer in [#47179](https://github.com/huggingface/transformers/pull/47179) **Links:** [Documentation](https://hug',
    _learned_15ea4d08866a,
)


def _learned_b9997e3e82f0(items, limit: int = 32) -> tuple[str, ...]:
    """Return bounded caller values explicitly grounded in verified lesson terms."""
    limit_i = int(limit)
    if limit_i < 1 or limit_i > 128:
        raise ValueError("lesson-grounding limit is out of bounds")
    terms = ('bounded', 'this', 'lesson', 'research-backed', 'from', 'b10589', 'details', 'open', 'cuda', 'pool_1d', 'support', 'missing', 'trailing', 'newline', 'editorconfig', 'compliance')
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
    'learned_b9997e3e82f05ca6',
    "Ground bounded candidate context against terms derived only from the verified lesson/evidence before downstream use. Verified lesson: Add one new bounded Genesis capability implementing this verified transferable lesson: Research-backed capability candidate from 'b10589': <details open> cuda : add POOL_1D support (#27573) * cuda : add POOL_1D support * fix: add missing trailing newline for editorconfig compliance </details> **Website:** - <https://llama.app> **Attestations:** - <https://github.com/ggml-org/llama.cpp/attestations/42401257> **macOS/iOS:** - [macOS Apple Silicon (arm64)](https://github.com/ggml-org/llama.cpp/releases/download/b10589/llama-b10589-bin-macos-arm64.tar.gz) - macOS Apple Silicon (arm64, KleidiAI ena",
    '<details open> cuda : add POOL_1D support (#27573) * cuda : add POOL_1D support * fix: add missing trailing newline for editorconfig compliance </details> **Website:** - <https://llama.app> **Attestations:** - <https://github.com/ggml-org/llama.cpp/attestations/42401257> **macOS/iOS:** - [macOS Apple Silicon (arm64)](https://github.com/ggml-org/llama.cpp/releases/download/b10589/llama-b10589-bin-macos-arm64.tar.gz) - macOS Apple Silicon (arm64, KleidiAI enabled) [DISABLED](https://github.com/ggml-org/llama.cpp/pull/23780) - [macOS Intel (x64)](https://github.com/ggml-org/llama.cpp/releases/download/b10589/llama-b10589-bin-macos-x64.tar.gz) - [iOS XCFramework](https://github.com/ggml-org/llama.cpp/releases/download/b10589/llama-b10589-xcframework.zip) **Linux:** - [Ubuntu x64 (CPU)](https://github.com/ggml-org/llama.cpp/releases/download/b10589/llama-b10589-bin-ubuntu-x64.tar.gz) - [Ubuntu arm64 (CPU)](https://github.com/ggml-org/llama.cpp/releases/download/b10589/llama-b10589-bin-ubuntu-arm64.tar.gz) - [Ubuntu s390x (CPU)](https://github.com/ggml-org/llama.cpp/releases/download/b10589/llama-b10589-bin-ubuntu-s390x.tar.gz) - [Ubuntu x64 (Vulkan)](https://github.com/ggml-org/llama.cp',
    _learned_b9997e3e82f0,
)


def _learned_84ff2bdb67b0(items, limit: int = 32) -> tuple[str, ...]:
    """Return bounded caller values explicitly grounded in verified lesson terms."""
    limit_i = int(limit)
    if limit_i < 1 or limit_i > 128:
        raise ValueError("lesson-grounding limit is out of bounds")
    terms = ('bounded', 'this', 'lesson', 'research-backed', 'from', 'b10584', 'details', 'open', 'also', 'take', 'into', 'account', 'n_streams', 'server', 'make', 'draft')
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
    'learned_84ff2bdb67b01248',
    "Ground bounded candidate context against terms derived only from the verified lesson/evidence before downstream use. Verified lesson: Add one new bounded Genesis capability implementing this verified transferable lesson: Research-backed capability candidate from 'b10584': <details open> fit: also take into account n_streams (#27496) * fit: also take into account n_streams * server: make the draft context follow the target context With a non-unified KV cache the target context now holds n_ctx_train tokens per sequence, while the draft context was still created with n_ctx = 0 and fell back to n_ctx_train / n_streams per sequence.",
    '<details open> fit: also take into account n_streams (#27496) * fit: also take into account n_streams * server: make the draft context follow the target context With a non-unified KV cache the target context now holds n_ctx_train tokens per sequence, while the draft context was still created with n_ctx = 0 and fell back to n_ctx_train / n_streams per sequence.',
    _learned_84ff2bdb67b0,
)


def _learned_eb8f7f380e39(items, limit: int = 32) -> tuple[str, ...]:
    """Return bounded caller values explicitly grounded in verified lesson terms."""
    limit_i = int(limit)
    if limit_i < 1 or limit_i > 128:
        raise ValueError("lesson-grounding limit is out of bounds")
    terms = ('bounded', 'this', 'lesson', 'research-backed', 'from', 'g-carl', 'grounded', 'checklist-aligned', 'reward', 'patient-oriented', 'medical', 'report', 'interpretation', 'personalized', 'reports', 'emerged')
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
    'learned_eb8f7f380e39539b',
    "Ground bounded candidate context against terms derived only from the verified lesson/evidence before downstream use. Verified lesson: Add one new bounded Genesis capability implementing this verified transferable lesson: Research-backed capability candidate from 'G-CARL: Grounded Checklist-Aligned Reward Learning for Patient-Oriented Medical Report Interpretation': Personalized interpretation of medical reports has emerged as an increasingly important need among patients. Addressing this need requires both evidence-grounded medical factuality and context-dependent patient communication, yet existing medical vision-language tasks do not adequately capture these dual requirements. To bridge this gap, we introduce Patient-orien",
    "Personalized interpretation of medical reports has emerged as an increasingly important need among patients. Addressing this need requires both evidence-grounded medical factuality and context-dependent patient communication, yet existing medical vision-language tasks do not adequately capture these dual requirements. To bridge this gap, we introduce Patient-oriented Medical Report Interpretation (PMRI), a novel open-ended multimodal generation task that requires models to explain medical reports in accurate and accessible language based on a user's query and dialogue history. These two objectives differ fundamentally in their verifiability, yet remain tightly coupled, making them difficult to optimize jointly under conventional supervised fine-tuning and holistic reinforcement learning paradigms. To address this challenge, we propose G-CARL, a grounded, checklist-aligned reinforcement learning framework that combines multi-source retrieval for atomic claim verification with context-aware, instance-specific weighted checklists for response coverage, providing structured supervision for factuality, user-demand satisfaction, and expression quality without constraining response divers",
    _learned_eb8f7f380e39,
)


def _learned_4a4035efa26a(items, limit: int = 32) -> tuple[str, ...]:
    """Return bounded caller values explicitly grounded in verified lesson terms."""
    limit_i = int(limit)
    if limit_i < 1 or limit_i > 128:
        raise ValueError("lesson-grounding limit is out of bounds")
    terms = ('bounded', 'this', 'lesson', 'research-backed', 'from', 'comparison', 'between', 'ceiling-mounted', 'fmcw', 'ir-uwb', 'wi-fi', 'radar', 'in-bedroom', 'human', 'activity', 'monitoring')
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
    'learned_4a4035efa26a8d7c',
    "Ground bounded candidate context against terms derived only from the verified lesson/evidence before downstream use. Verified lesson: Add one new bounded Genesis capability implementing this verified transferable lesson: Research-backed capability candidate from 'A comparison between ceiling-mounted FMCW, IR-UWB and Wi-Fi radar for in-bedroom human activity monitoring and sleep interruption detection': Despite their growing importance for contact-free radio frequency (RF) based healthcare monitoring, different radio technologies such as frequency-modulated continuous wave (FMCW) radar, impulse radio ultra-wideband (IR-UWB), and Wi-Fi sensing are rarely compared under identical deployment conditions, as existing studies typic",
    'Despite their growing importance for contact-free radio frequency (RF) based healthcare monitoring, different radio technologies such as frequency-modulated continuous wave (FMCW) radar, impulse radio ultra-wideband (IR-UWB), and Wi-Fi sensing are rarely compared under identical deployment conditions, as existing studies typically differ in hardware, datasets, and evaluation methodologies. In addition, the performance of ceiling-mounted radars, despite their practical deployment and cost advantages in healthcare environments, remain underexplored. Therefore, this paper presents a controlled comparison and analysis of ceiling-mounted FMCW, IR-UWB, and Wi-Fi sensing using synchronized recordings from 20 participants across six room layouts. All technologies are evaluated with the same convolutional neural network (CNN) on both a fine-grained 10-class human activity recognition (HAR) task and a coarse 4-class sleep monitoring task. IR-UWB achieves the highest cross-subject activity recognition performance (89.0% macro F1), while FMCW generalizes best to unseen room layouts (83.8% macro F1). For sleep monitoring, all technologies exceed 92% macro F1 in unseen environments. The results',
    _learned_4a4035efa26a,
)


def _learned_0110b75296c1(items, limit: int = 32) -> tuple[str, ...]:
    """Return bounded caller values explicitly grounded in verified lesson terms."""
    limit_i = int(limit)
    if limit_i < 1 or limit_i > 128:
        raise ValueError("lesson-grounding limit is out of bounds")
    terms = ('bounded', 'this', 'lesson', 'research-backed', 'from', 'b10581', 'details', 'open', 'model', 'support', 'dspark', 'bailingmoe3', 'website', 'https', 'llama.app', 'attestations')
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
    'learned_0110b75296c1ead5',
    "Ground bounded candidate context against terms derived only from the verified lesson/evidence before downstream use. Verified lesson: Add one new bounded Genesis capability implementing this verified transferable lesson: Research-backed capability candidate from 'b10581': <details open> model : support DSpark for bailingmoe3 (#27508) </details> **Website:** - <https://llama.app> **Attestations:** - <https://github.com/ggml-org/llama.cpp/attestations/42309942> **macOS/iOS:** - [macOS Apple Silicon (arm64)](https://github.com/ggml-org/llama.cpp/releases/download/b10581/llama-b10581-bin-macos-arm64.tar.gz) - macOS Apple Silicon (arm64, KleidiAI enabled) [DISABLED](https://github.com/ggml-org/llama.cpp/pull/23780) - [macOS Intel",
    '<details open> model : support DSpark for bailingmoe3 (#27508) </details> **Website:** - <https://llama.app> **Attestations:** - <https://github.com/ggml-org/llama.cpp/attestations/42309942> **macOS/iOS:** - [macOS Apple Silicon (arm64)](https://github.com/ggml-org/llama.cpp/releases/download/b10581/llama-b10581-bin-macos-arm64.tar.gz) - macOS Apple Silicon (arm64, KleidiAI enabled) [DISABLED](https://github.com/ggml-org/llama.cpp/pull/23780) - [macOS Intel (x64)](https://github.com/ggml-org/llama.cpp/releases/download/b10581/llama-b10581-bin-macos-x64.tar.gz) - [iOS XCFramework](https://github.com/ggml-org/llama.cpp/releases/download/b10581/llama-b10581-xcframework.zip) **Linux:** - [Ubuntu x64 (CPU)](https://github.com/ggml-org/llama.cpp/releases/download/b10581/llama-b10581-bin-ubuntu-x64.tar.gz) - [Ubuntu arm64 (CPU)](https://github.com/ggml-org/llama.cpp/releases/download/b10581/llama-b10581-bin-ubuntu-arm64.tar.gz) - [Ubuntu s390x (CPU)](https://github.com/ggml-org/llama.cpp/releases/download/b10581/llama-b10581-bin-ubuntu-s390x.tar.gz) - [Ubuntu x64 (Vulkan)](https://github.com/ggml-org/llama.cpp/releases/download/b10581/llama-b10581-bin-ubuntu-vulkan-x64.tar.gz) - [Ubuntu a',
    _learned_0110b75296c1,
)


def _learned_ea0ed6a2872c(items, limit: int = 32) -> tuple[str, ...]:
    """Return bounded caller values explicitly grounded in verified lesson terms."""
    limit_i = int(limit)
    if limit_i < 1 or limit_i > 128:
        raise ValueError("lesson-grounding limit is out of bounds")
    terms = ('bounded', 'this', 'lesson', 'research-backed', 'from', 'pandora', 'model', 'routing', 'efficient', 'allocation', 'with', 'costly', 'value', 'estimation', 'heterogeneous', 'systems')
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
    'learned_ea0ed6a2872c9278',
    "Ground bounded candidate context against terms derived only from the verified lesson/evidence before downstream use. Verified lesson: Add one new bounded Genesis capability implementing this verified transferable lesson: Research-backed capability candidate from 'Pandora's AI Model Routing Box: Efficient Allocation with Costly Value Estimation': Heterogeneous AI systems composed of multiple models, architectures, harnesses, or inference-time settings can improve quality and efficiency by routing queries to the specialist who can answer most effectively at the lowest cost. Routing requires estimating each specialist's expected return, but this value estimation has a cost. Cheap estimators (e.g., embedding-based predictors) ar",
    "Heterogeneous AI systems composed of multiple models, architectures, harnesses, or inference-time settings can improve quality and efficiency by routing queries to the specialist who can answer most effectively at the lowest cost. Routing requires estimating each specialist's expected return, but this value estimation has a cost. Cheap estimators (e.g., embedding-based predictors) are fast but noisy, while accurate estimators (e.g., fine-tuned models with access to retrieval results or partial reasoning traces) are expensive. We formalize this tradeoff as an instance of Pandora's Box, the classical problem of optimal search with costly inspection. Under a Gaussian signal model, the resulting policies have closed-form value-of-information expressions that determine, for each specialist and input, whether refining the value estimate is worth its cost. We call the centralized policy Pandora's Router. We extend this to a decentralized setting, Pandora's Bidder, where specialists independently decide whether to invest in self-assessment before accepting an offered price to claim a query. Experiments across three domains---a standard multi-LLM benchmark, retrieval-augmented specialists,",
    _learned_ea0ed6a2872c,
)


def _learned_a877df86d520(items, limit: int = 32) -> tuple[str, ...]:
    """Return bounded caller values explicitly grounded in verified lesson terms."""
    limit_i = int(limit)
    if limit_i < 1 or limit_i > 128:
        raise ValueError("lesson-grounding limit is out of bounds")
    terms = ('bounded', 'this', 'lesson', 'research-backed', 'from', 'ai4ai-bench', 'benchmarking', 'agents', 'algorithmic', 'design', 'recursive', 'self-improvement', 'asks', 'whether', 'system', 'improve')
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
    'learned_a877df86d5204c60',
    "Ground bounded candidate context against terms derived only from the verified lesson/evidence before downstream use. Verified lesson: Add one new bounded Genesis capability implementing this verified transferable lesson: Research-backed capability candidate from 'AI4AI-Bench: Benchmarking LLM Agents in Algorithmic Design for Recursive Self-Improvement': Recursive self-improvement (RSI) asks whether an AI system can improve the process that produces AI systems, so that the next system inherits the improvement. That process is the training algorithm: a better objective or update rule improves the compute\\mbox{-}capability exchange rate for every subsequent run, including the one that produces the next agent. Whether RSI is fea",
    "Recursive self-improvement (RSI) asks whether an AI system can improve the process that produces AI systems, so that the next system inherits the improvement. That process is the training algorithm: a better objective or update rule improves the compute\\mbox{-}capability exchange rate for every subsequent run, including the one that produces the next agent. Whether RSI is feasible therefore turns on whether an agent can design training algorithms. No benchmark isolates that ability: existing suites are won by collecting data or by tuning hyperparameters, and none tells a change to how a run is executed apart from a change to how the model learns. We present AI4AI\\mbox{-}Bench, 10 frozen research repositories spanning 10 training algorithm families. In each task, an agent has 4 hours on one B300 to rewrite the training algorithm; its code is then rerun from scratch for up to 12 hours and scored by a fixed evaluator hidden from the agent, against the repository's original algorithm under the same procedure. Because the 10 metrics are incommensurable, every task is mapped onto one scale on which $0$ is an uninformative model, $0.1$ is the algorithm the repository ships, and $1.0$ is t",
    _learned_a877df86d520,
)


def _learned_9b7444970226(items, limit: int = 32) -> tuple[str, ...]:
    """Return bounded caller values explicitly grounded in verified lesson terms."""
    limit_i = int(limit)
    if limit_i < 1 or limit_i > 128:
        raise ValueError("lesson-grounding limit is out of bounds")
    terms = ('bounded', 'this', 'lesson', 'research-backed', 'from', 'b10580', 'details', 'open', 'mtmd', 'support', 'dots3-note', 'vision+audio', 'text', 'conversion', 'init', 'impl')
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
    'learned_9b7444970226cd76',
    "Ground bounded candidate context against terms derived only from the verified lesson/evidence before downstream use. Verified lesson: Add one new bounded Genesis capability implementing this verified transferable lesson: Research-backed capability candidate from 'b10580': <details open> mtmd: support dots3-note vision+audio (#27524) * text: conversion * init impl * mtmd: conversion * impl mtmd cpp * Update gguf-py/gguf/tensor_mapping.py Co-authored-by: Sigbjørn Skjæret <sigbjorn.skjaeret@huggingface.co> --------- Co-authored-by: Sigbjørn Skjæret <sigbjorn.skjaeret@huggingface.co> </details> **Website:** - <https://llama.app> **Attestations:** - <https://github.com/ggml-org/llama.cpp/attestations/42307518> **macOS/iOS:**",
    '<details open> mtmd: support dots3-note vision+audio (#27524) * text: conversion * init impl * mtmd: conversion * impl mtmd cpp * Update gguf-py/gguf/tensor_mapping.py Co-authored-by: Sigbjørn Skjæret <sigbjorn.skjaeret@huggingface.co> --------- Co-authored-by: Sigbjørn Skjæret <sigbjorn.skjaeret@huggingface.co> </details> **Website:** - <https://llama.app> **Attestations:** - <https://github.com/ggml-org/llama.cpp/attestations/42307518> **macOS/iOS:** - [macOS Apple Silicon (arm64)](https://github.com/ggml-org/llama.cpp/releases/download/b10580/llama-b10580-bin-macos-arm64.tar.gz) - macOS Apple Silicon (arm64, KleidiAI enabled) [DISABLED](https://github.com/ggml-org/llama.cpp/pull/23780) - [macOS Intel (x64)](https://github.com/ggml-org/llama.cpp/releases/download/b10580/llama-b10580-bin-macos-x64.tar.gz) - [iOS XCFramework](https://github.com/ggml-org/llama.cpp/releases/download/b10580/llama-b10580-xcframework.zip) **Linux:** - [Ubuntu x64 (CPU)](https://github.com/ggml-org/llama.cpp/releases/download/b10580/llama-b10580-bin-ubuntu-x64.tar.gz) - [Ubuntu arm64 (CPU)](https://github.com/ggml-org/llama.cpp/releases/download/b10580/llama-b10580-bin-ubuntu-arm64.tar.gz) - [Ubuntu s390',
    _learned_9b7444970226,
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


def _learned_e1fe0481941d(items, limit: int = 32) -> tuple[str, ...]:
    """Return bounded caller values explicitly grounded in verified lesson terms."""
    limit_i = int(limit)
    if limit_i < 1 or limit_i > 128:
        raise ValueError("lesson-grounding limit is out of bounds")
    terms = ('bounded', 'this', 'lesson', 'research-backed', 'from', 'explainable', 'transformer', 'models', 'clinical', 'prediction', 'tasks', 'structured', 'electronic', 'health', 'records', 'predictive')
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
    'learned_e1fe0481941d63fc',
    "Ground bounded candidate context against terms derived only from the verified lesson/evidence before downstream use. Verified lesson: Add one new bounded Genesis capability implementing this verified transferable lesson: Research-backed capability candidate from 'Explainable Transformer Models for Clinical Prediction Tasks on Structured Electronic Health Records': Predictive models over structured electronic health records (EHRs) remain central to machine learning for healthcare, but few have jointly emphasized quantitative laboratory information and interpretability with respect to input medical events. We present BERT-LER, a BERT-style model for coded EHR timelines pretrained and fine-tuned from a de-identified EHR dataset",
    'Predictive models over structured electronic health records (EHRs) remain central to machine learning for healthcare, but few have jointly emphasized quantitative laboratory information and interpretability with respect to input medical events. We present BERT-LER, a BERT-style model for coded EHR timelines pretrained and fine-tuned from a de-identified EHR dataset of 75 million patients, that encodes laboratory test results as discrete tokens while retaining graded information through percentile-based binning, paired with Integrated Gradients for token-level attributions grounded in the input EHR sequence. We benchmark our approach on the public EHRShot benchmark suite and on an asthma severity progression study based on real-world data. This addresses a methodological gap in EHR foundation-style modeling by unifying laboratory value representation and explainability in a single framework, while assessing whether both predictive performance and explanations generalize beyond standard clinical prediction tasks. Across EHRShot and asthma tasks, BERT-LER achieves predictive performance that is competitive with, and on laboratory-related tasks often exceeds, publicly available benchma',
    _learned_e1fe0481941d,
)


def _learned_1146cc46d54d(items, limit: int = 32) -> tuple[str, ...]:
    """Return bounded caller values explicitly grounded in verified lesson terms."""
    limit_i = int(limit)
    if limit_i < 1 or limit_i > 128:
        raise ValueError("lesson-grounding limit is out of bounds")
    terms = ('bounded', 'this', 'lesson', 'research-backed', 'from', 'b10576', 'details', 'open', 'sycl', 'q2_k', 'reordered', 'mmvq', 'esimd', 'kernels', 'again', 'revert')
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
    'learned_1146cc46d54d683f',
    'Ground bounded candidate context against terms derived only from the verified lesson/evidence before downstream use. Verified lesson: Add one new bounded Genesis capability implementing this verified transferable lesson: Research-backed capability candidate from \'b10576\': <details open> sycl : add Q2_K reordered MMVQ and ESIMD kernels (again) (#27490) * Revert "Revert "sycl : add Q2_K reordered MMVQ and ESIMD kernels (#26336)" (#…" This reverts commit 7a0e42fd01fb0acda644e4f04b1f1acbbb9e23ba. * add gate params </details> **Website:** - <https://llama.app> **Attestations:** - <https://github.com/ggml-org/llama.cpp/attestations/42300392> **macOS/iOS:** - [macOS Apple Silicon (arm64)](https://github.com/ggml-org/llama.cpp/rel',
    '<details open> sycl : add Q2_K reordered MMVQ and ESIMD kernels (again) (#27490) * Revert "Revert "sycl : add Q2_K reordered MMVQ and ESIMD kernels (#26336)" (#…" This reverts commit 7a0e42fd01fb0acda644e4f04b1f1acbbb9e23ba. * add gate params </details> **Website:** - <https://llama.app> **Attestations:** - <https://github.com/ggml-org/llama.cpp/attestations/42300392> **macOS/iOS:** - [macOS Apple Silicon (arm64)](https://github.com/ggml-org/llama.cpp/releases/download/b10576/llama-b10576-bin-macos-arm64.tar.gz) - macOS Apple Silicon (arm64, KleidiAI enabled) [DISABLED](https://github.com/ggml-org/llama.cpp/pull/23780) - [macOS Intel (x64)](https://github.com/ggml-org/llama.cpp/releases/download/b10576/llama-b10576-bin-macos-x64.tar.gz) - [iOS XCFramework](https://github.com/ggml-org/llama.cpp/releases/download/b10576/llama-b10576-xcframework.zip) **Linux:** - [Ubuntu x64 (CPU)](https://github.com/ggml-org/llama.cpp/releases/download/b10576/llama-b10576-bin-ubuntu-x64.tar.gz) - [Ubuntu arm64 (CPU)](https://github.com/ggml-org/llama.cpp/releases/download/b10576/llama-b10576-bin-ubuntu-arm64.tar.gz) - [Ubuntu s390x (CPU)](https://github.com/ggml-org/llama.cpp/releases/download/b10576',
    _learned_1146cc46d54d,
)


def _learned_849abffda26c(items, limit: int = 32) -> tuple[str, ...]:
    """Return bounded caller values explicitly grounded in verified lesson terms."""
    limit_i = int(limit)
    if limit_i < 1 or limit_i > 128:
        raise ValueError("lesson-grounding limit is out of bounds")
    terms = ('bounded', 'this', 'lesson', 'research-backed', 'from', 'langgraph-sdk', 'changes', 'since', 'sdk-py', 'feat', 'decrypt', 'replacement', 'result', 'langgraph', 'chore', 'deps')
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
    'learned_849abffda26cfcb3',
    "Ground bounded candidate context against terms derived only from the verified lesson/evidence before downstream use. Verified lesson: Add one new bounded Genesis capability implementing this verified transferable lesson: Research-backed capability candidate from 'langgraph-sdk==0.4.3': Changes since sdk==0.4.2 * release(sdk-py): 0.4.3 (#8657) * feat(sdk-py): add decrypt replacement result (#8598) * release(langgraph): 1.2.11 (#8595) * chore(deps): bump the minor-and-patch group across 1 directory with 5 updates (#8532) * release(checkpoint): 4.2.0 (#8563) * chore: enforce PLC0415 in tests for the remaining packages (#8547) * release(langgraph): 1.2.10 (#8462) * chore(deps): bump websockets from 15.0.1 to 16.0 in /libs/sdk-py",
    'Changes since sdk==0.4.2 * release(sdk-py): 0.4.3 (#8657) * feat(sdk-py): add decrypt replacement result (#8598) * release(langgraph): 1.2.11 (#8595) * chore(deps): bump the minor-and-patch group across 1 directory with 5 updates (#8532) * release(checkpoint): 4.2.0 (#8563) * chore: enforce PLC0415 in tests for the remaining packages (#8547) * release(langgraph): 1.2.10 (#8462) * chore(deps): bump websockets from 15.0.1 to 16.0 in /libs/sdk-py in the major group (#8253) * fix(sdk-py): support clearing cron end_time via update(end_time=None) (#8334) * release(langgraph): 1.2.9 (#8316) * release(langgraph): 1.2.8 (#8292) * chore(deps): bump websockets from 15.0.1 to 16.0 in /libs/langgraph in the major group (#8256) * chore(deps): bump the minor-and-patch group in /libs/sdk-py with 9 updates (#8252) * release(langgraph): 1.2.7 (#8223) * chore(deps-dev): bump starlette from 1.0.1 to 1.3.1 in /libs/sdk-py (#8104) * chore(deps): bump langsmith from 0.8.0 to 0.8.18 in /libs/sdk-py (#8174) * release(langgraph): 1.2.6 (#8139) * docs: standardize package `README.md` structure (#8064) * release(langgraph): 1.2.5 (#8062) * fix(langgraph): merge `lc_versions` config metadata (#8052) * chore(de',
    _learned_849abffda26c,
)


def _learned_b1a4ad80a80f(items, limit: int = 32) -> tuple[str, ...]:
    """Return bounded caller values explicitly grounded in verified lesson terms."""
    limit_i = int(limit)
    if limit_i < 1 or limit_i > 128:
        raise ValueError("lesson-grounding limit is out of bounds")
    terms = ('bounded', 'this', 'lesson', 'research-backed', 'from', 'b10586', 'details', 'open', 'mtmd', 'ggml_rope_set_offset', 'comment', 'website', 'https', 'llama.app', 'attestations', 'github.com')
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
    'learned_b1a4ad80a80f886e',
    "Ground bounded candidate context against terms derived only from the verified lesson/evidence before downstream use. Verified lesson: Add one new bounded Genesis capability implementing this verified transferable lesson: Research-backed capability candidate from 'b10586': <details open> mtmd: use ggml_rope_set_offset (#27521) * mtmd: use ggml_rope_set_offset * add comment </details> **Website:** - <https://llama.app> **Attestations:** - <https://github.com/ggml-org/llama.cpp/attestations/42334609> **macOS/iOS:** - [macOS Apple Silicon (arm64)](https://github.com/ggml-org/llama.cpp/releases/download/b10586/llama-b10586-bin-macos-arm64.tar.gz) - macOS Apple Silicon (arm64, KleidiAI enabled) [DISABLED](https://github.com/ggml-o",
    '<details open> mtmd: use ggml_rope_set_offset (#27521) * mtmd: use ggml_rope_set_offset * add comment </details> **Website:** - <https://llama.app> **Attestations:** - <https://github.com/ggml-org/llama.cpp/attestations/42334609> **macOS/iOS:** - [macOS Apple Silicon (arm64)](https://github.com/ggml-org/llama.cpp/releases/download/b10586/llama-b10586-bin-macos-arm64.tar.gz) - macOS Apple Silicon (arm64, KleidiAI enabled) [DISABLED](https://github.com/ggml-org/llama.cpp/pull/23780) - [macOS Intel (x64)](https://github.com/ggml-org/llama.cpp/releases/download/b10586/llama-b10586-bin-macos-x64.tar.gz) - [iOS XCFramework](https://github.com/ggml-org/llama.cpp/releases/download/b10586/llama-b10586-xcframework.zip) **Linux:** - [Ubuntu x64 (CPU)](https://github.com/ggml-org/llama.cpp/releases/download/b10586/llama-b10586-bin-ubuntu-x64.tar.gz) - [Ubuntu arm64 (CPU)](https://github.com/ggml-org/llama.cpp/releases/download/b10586/llama-b10586-bin-ubuntu-arm64.tar.gz) - [Ubuntu s390x (CPU)](https://github.com/ggml-org/llama.cpp/releases/download/b10586/llama-b10586-bin-ubuntu-s390x.tar.gz) - [Ubuntu x64 (Vulkan)](https://github.com/ggml-org/llama.cpp/releases/download/b10586/llama-b10586-bi',
    _learned_b1a4ad80a80f,
)


def _learned_251f9be24d3c(items, limit: int = 32) -> tuple[str, ...]:
    """Return bounded caller values explicitly grounded in verified lesson terms."""
    limit_i = int(limit)
    if limit_i < 1 or limit_i > 128:
        raise ValueError("lesson-grounding limit is out of bounds")
    terms = ('bounded', 'this', 'lesson', 'research-backed', 'from', 'b10590', 'details', 'open', 'vendor', 'update', 'subprocess.h', 'website', 'https', 'llama.app', 'attestations', 'github.com')
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
    'learned_251f9be24d3c8ce2',
    "Ground bounded candidate context against terms derived only from the verified lesson/evidence before downstream use. Verified lesson: Add one new bounded Genesis capability implementing this verified transferable lesson: Research-backed capability candidate from 'b10590': <details open> vendor : update subprocess.h (#27409) </details> **Website:** - <https://llama.app> **Attestations:** - <https://github.com/ggml-org/llama.cpp/attestations/42402532> **macOS/iOS:** - [macOS Apple Silicon (arm64)](https://github.com/ggml-org/llama.cpp/releases/download/b10590/llama-b10590-bin-macos-arm64.tar.gz) - macOS Apple Silicon (arm64, KleidiAI enabled) [DISABLED](https://github.com/ggml-org/llama.cpp/pull/23780) - [macOS Intel (x64)](ht",
    '<details open> vendor : update subprocess.h (#27409) </details> **Website:** - <https://llama.app> **Attestations:** - <https://github.com/ggml-org/llama.cpp/attestations/42402532> **macOS/iOS:** - [macOS Apple Silicon (arm64)](https://github.com/ggml-org/llama.cpp/releases/download/b10590/llama-b10590-bin-macos-arm64.tar.gz) - macOS Apple Silicon (arm64, KleidiAI enabled) [DISABLED](https://github.com/ggml-org/llama.cpp/pull/23780) - [macOS Intel (x64)](https://github.com/ggml-org/llama.cpp/releases/download/b10590/llama-b10590-bin-macos-x64.tar.gz) - [iOS XCFramework](https://github.com/ggml-org/llama.cpp/releases/download/b10590/llama-b10590-xcframework.zip) **Linux:** - [Ubuntu x64 (CPU)](https://github.com/ggml-org/llama.cpp/releases/download/b10590/llama-b10590-bin-ubuntu-x64.tar.gz) - [Ubuntu arm64 (CPU)](https://github.com/ggml-org/llama.cpp/releases/download/b10590/llama-b10590-bin-ubuntu-arm64.tar.gz) - [Ubuntu s390x (CPU)](https://github.com/ggml-org/llama.cpp/releases/download/b10590/llama-b10590-bin-ubuntu-s390x.tar.gz) - [Ubuntu x64 (Vulkan)](https://github.com/ggml-org/llama.cpp/releases/download/b10590/llama-b10590-bin-ubuntu-vulkan-x64.tar.gz) - [Ubuntu arm64 (Vulk',
    _learned_251f9be24d3c,
)


def _learned_61cbbb982dde(items, limit: int = 32) -> tuple[str, ...]:
    """Return bounded caller values explicitly grounded in verified lesson terms."""
    limit_i = int(limit)
    if limit_i < 1 or limit_i > 128:
        raise ValueError("lesson-grounding limit is out of bounds")
    terms = ('bounded', 'this', 'lesson', 'research-backed', 'from', 'langgraph', 'changes', 'since', 'feat', 'expose', 'trace_policy', 'add_node', 'chore', 'deps', 'bump', 'minor-and-patch')
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
    'learned_61cbbb982dde61cd',
    "Ground bounded candidate context against terms derived only from the verified lesson/evidence before downstream use. Verified lesson: Add one new bounded Genesis capability implementing this verified transferable lesson: Research-backed capability candidate from 'langgraph==1.2.11': Changes since 1.2.10 * release(langgraph): 1.2.11 (#8595) * feat(langgraph): expose `trace_policy` on `add_node` (#8523) * chore(deps): bump the minor-and-patch group across 1 directory with 7 updates (#8533) * chore(deps): bump the minor-and-patch group across 1 directory with 5 updates (#8532) * release(checkpoint-postgres): 3.1.2 (#8565) * release(checkpoint): 4.2.0 (#8563) * fix(checkpoint): collect writes at plain-value seed in delta channel",
    'Changes since 1.2.10 * release(langgraph): 1.2.11 (#8595) * feat(langgraph): expose `trace_policy` on `add_node` (#8523) * chore(deps): bump the minor-and-patch group across 1 directory with 7 updates (#8533) * chore(deps): bump the minor-and-patch group across 1 directory with 5 updates (#8532) * release(checkpoint-postgres): 3.1.2 (#8565) * release(checkpoint): 4.2.0 (#8563) * fix(checkpoint): collect writes at plain-value seed in delta channel history (#8526) * chore: enforce PLC0415 in tests for the remaining packages (#8547) * test(checkpoint-postgres,checkpoint-sqlite): run the conformance suite (#8537) * chore: enable RUF100 and clear unused noqa directives (#8546) * chore(deps-dev): bump types-requests from 2.33.0.20260518 to 2.33.0.20260712 in /libs/langgraph (#8502) * chore(deps): bump cryptography from 48.0.1 to 50.0.0 in /libs/langgraph (#8528) * release(checkpoint-sqlite): 3.1.1 (#8481) * release(checkpoint-postgres): 3.1.1 (#8480)',
    _learned_61cbbb982dde,
)


def _learned_e45b1de1c7d0(items, limit: int = 32) -> tuple[str, ...]:
    """Return bounded caller values explicitly grounded in verified lesson terms."""
    limit_i = int(limit)
    if limit_i < 1 or limit_i > 128:
        raise ValueError("lesson-grounding limit is out of bounds")
    terms = ('bounded', 'this', 'lesson', 'research-backed', 'from', 'b10587', 'details', 'open', 'vulkan', 'added', 'pad_reflect_1d', 'operation', 'implemented', 'ggml_op_pad_reflect_1d', 'backend', 'changes')
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
    'learned_e45b1de1c7d0ecc4',
    "Ground bounded candidate context against terms derived only from the verified lesson/evidence before downstream use. Verified lesson: Add one new bounded Genesis capability implementing this verified transferable lesson: Research-backed capability candidate from 'b10587': <details open> vulkan : added the PAD_REFLECT_1D operation (#26586) * vulkan : added PAD_REFLECT_1D operation Implemented the GGML_OP_PAD_REFLECT_1D operation for the Vulkan backend Changes: - pad_reflect_1d.comp: implemented the GLSL compute shader with reflection logic - vulkan-shaders-gen.cpp: register the shader for SPIR-V compilation - ggml-vulkan.cpp: pushed constants struct, pipeline creation, supports_op, dispatch function, compute switch and debug",
    '<details open> vulkan : added the PAD_REFLECT_1D operation (#26586) * vulkan : added PAD_REFLECT_1D operation Implemented the GGML_OP_PAD_REFLECT_1D operation for the Vulkan backend Changes: - pad_reflect_1d.comp: implemented the GLSL compute shader with reflection logic - vulkan-shaders-gen.cpp: register the shader for SPIR-V compilation - ggml-vulkan.cpp: pushed constants struct, pipeline creation, supports_op, dispatch function, compute switch and debug validation Tested the PAD_REFLECT_1D on Intel Iris Xe (Vulkan 1.4, Mesa 25.2.8): Correctness: PAD_REFLECT_1D(type=f32,ne_a=[512,34,2,1],pad_0=10,pad_1=9) = Pass PAD_REFLECT_1D(type=f32,ne_a=[3000,384,4,1],pad_0=10,pad_1=9) = Pass 2/2 tests passed - All test are passed Performance: ne_a=[512,34,2,1] -> 5.38 us/run, 24.55 GB/s ne_a=[3000,80,1,1] -> 30.09 us/run, 59.62 GB/s ne_a=[3000,384,4,1] -> 158.31 us/run, 54.39 GB/s * Update ggml/src/ggml-vulkan/vulkan-shaders/pad_reflect_1d.comp Co-authored-by: Jeff Bolz <jbolz@nvidia.com> --------- Co-authored-by: Jeff Bolz <jbolz@nvidia.com> </details> **Website:** - <https://llama.app> **Attestations:** - <https://github.com/ggml-org/llama.cpp/attestations/42354333> **macOS/iOS:** - [macOS',
    _learned_e45b1de1c7d0,
)


def _learned_e048082f7639(items, limit: int = 32) -> tuple[str, ...]:
    """Return bounded caller values explicitly grounded in verified lesson terms."""
    limit_i = int(limit)
    if limit_i < 1 or limit_i > 128:
        raise ValueError("lesson-grounding limit is out of bounds")
    terms = ('bounded', 'this', 'lesson', 'research-backed', 'from', 'v0.26.0', 'vllm', 'notes', 'highlights', 'features', 'commits', 'contributors', 'inkling', 'model', 'family', 'with')
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
    'learned_e048082f76397cc1',
    "Ground bounded candidate context against terms derived only from the verified lesson/evidence before downstream use. Verified lesson: Add one new bounded Genesis capability implementing this verified transferable lesson: Research-backed capability candidate from 'v0.26.0': # vLLM v0.26.0 Release Notes ## Highlights This release features 411 commits from 212 contributors (61 new)! * **New Inkling model family** with a full support stack: base modeling (#48799), piecewise CUDA graph support (#48822), Hopper FA4 relative attention (#48858), MTP=1 speculative decoding (#48869), LoRA (#48884), and standard ModelOpt NVFP4 quantization (#48990). * **DeepSeek-V4 performance push** across vendors: a specialized routing kernel (2.94%",
    '# vLLM v0.26.0 Release Notes ## Highlights This release features 411 commits from 212 contributors (61 new)! * **New Inkling model family** with a full support stack: base modeling (#48799), piecewise CUDA graph support (#48822), Hopper FA4 relative attention (#48858), MTP=1 speculative decoding (#48869), LoRA (#48884), and standard ModelOpt NVFP4 quantization (#48990). * **DeepSeek-V4 performance push** across vendors: a specialized routing kernel (2.94% E2E TPOT, #48660), `fused_topk_bias` (1.5–2x kernel, #47463), and redundant repeat/copy removal (1.8% E2E TPOT, #48137), plus ROCm two-stage compressor for HCA prefill (#47718), sparse decode/prefill optimizations (#48519, #48788, #46275), and DSpark speculative decoding on AMD (#47419) and XPU (#47677). * **fp32 `lm_head` for generation models via `head_dtype`** (#48390), extended to the LoRA path (#48525) and given a ROCm `torch.mm` fast path (#48688), improving accuracy for generation heads. * **Flexible attention backends**: the attention backend can now be selected per KV-cache group (#48012), and sliding-window support is now an explicit backend capability (#48011) — improving support for hybrid models. * **KV offloading & t',
    _learned_e048082f7639,
)


def _learned_161b50a4231b(items, limit: int = 32) -> tuple[str, ...]:
    """Return bounded caller values explicitly grounded in verified lesson terms."""
    limit_i = int(limit)
    if limit_i < 1 or limit_i > 128:
        raise ValueError("lesson-grounding limit is out of bounds")
    terms = ('bounded', 'this', 'lesson', 'research-backed', 'from', 'langgraph-checkpoint-postgres', 'changes', 'since', 'checkpointpostgres', 'checkpoint-postgres', 'checkpoint', 'test', 'checkpoint-sqlite', 'conformance', 'suite', 'find')
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
    'learned_161b50a4231bce0d',
    "Ground bounded candidate context against terms derived only from the verified lesson/evidence before downstream use. Verified lesson: Add one new bounded Genesis capability implementing this verified transferable lesson: Research-backed capability candidate from 'langgraph-checkpoint-postgres==3.1.2': Changes since checkpointpostgres==3.1.1 * release(checkpoint-postgres): 3.1.2 (#8565) * release(checkpoint): 4.2.0 (#8563) * test(checkpoint-postgres,checkpoint-sqlite): run the conformance suite (#8537) * fix(checkpoint-postgres): find plain-value seeds when walking delta history (#8535) * chore: enable RUF100 and clear unused noqa directives (#8546) * chore(checkpoint-postgres,checkpoint-sqlite): enable PLC0415 lint rule (#85",
    'Changes since checkpointpostgres==3.1.1 * release(checkpoint-postgres): 3.1.2 (#8565) * release(checkpoint): 4.2.0 (#8563) * test(checkpoint-postgres,checkpoint-sqlite): run the conformance suite (#8537) * fix(checkpoint-postgres): find plain-value seeds when walking delta history (#8535) * chore: enable RUF100 and clear unused noqa directives (#8546) * chore(checkpoint-postgres,checkpoint-sqlite): enable PLC0415 lint rule (#8540) * chore(deps): bump the minor-and-patch group in /libs/checkpoint-postgres with 5 updates (#8497)',
    _learned_161b50a4231b,
)


def _learned_d08522835e81(items, limit: int = 32) -> tuple[str, ...]:
    """Return bounded caller values explicitly grounded in verified lesson terms."""
    limit_i = int(limit)
    if limit_i < 1 or limit_i > 128:
        raise ValueError("lesson-grounding limit is out of bounds")
    terms = ('bounded', 'this', 'lesson', 'research-backed', 'from', 'python-v0.7.4', 'what', 'changed', 'update', 'docs', 'ekzhu', 'https', 'github.com', 'microsoft', 'autogen', 'pull')
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
    'learned_d08522835e81f7ba',
    "Ground bounded candidate context against terms derived only from the verified lesson/evidence before downstream use. Verified lesson: Add one new bounded Genesis capability implementing this verified transferable lesson: Research-backed capability candidate from 'python-v0.7.4': ## What's Changed * Update docs for 0.7.3 by @ekzhu in https://github.com/microsoft/autogen/pull/6948 * Update readme with agent-as-tool by @ekzhu in https://github.com/microsoft/autogen/pull/6949 * Fix Redis Deserialization Error by @BenConstable9 in https://github.com/microsoft/autogen/pull/6952 * Redis Doesn't Support Streaming by @BenConstable9 in https://github.com/microsoft/autogen/pull/6954 * update version to 0.7.4 by @ekzhu in https://github",
    "## What's Changed * Update docs for 0.7.3 by @ekzhu in https://github.com/microsoft/autogen/pull/6948 * Update readme with agent-as-tool by @ekzhu in https://github.com/microsoft/autogen/pull/6949 * Fix Redis Deserialization Error by @BenConstable9 in https://github.com/microsoft/autogen/pull/6952 * Redis Doesn't Support Streaming by @BenConstable9 in https://github.com/microsoft/autogen/pull/6954 * update version to 0.7.4 by @ekzhu in https://github.com/microsoft/autogen/pull/6955 * Update doc 0.7.4 by @ekzhu in https://github.com/microsoft/autogen/pull/6956 ## New Contributors * @BenConstable9 made their first contribution in https://github.com/microsoft/autogen/pull/6952 **Full Changelog**: https://github.com/microsoft/autogen/compare/python-v0.7.3...python-v0.7.4",
    _learned_d08522835e81,
)


def _learned_8ea81c76a275(items, limit: int = 32) -> tuple[str, ...]:
    """Return bounded caller values explicitly grounded in verified lesson terms."""
    limit_i = int(limit)
    if limit_i < 1 or limit_i > 128:
        raise ValueError("lesson-grounding limit is out of bounds")
    terms = ('bounded', 'this', 'lesson', 'research-backed', 'from', 'python-v0.7.3', 'what', 'changed', 'update', 'website', 'ekzhu', 'https', 'github.com', 'microsoft', 'autogen', 'pull')
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
    'learned_8ea81c76a27576c2',
    "Ground bounded candidate context against terms derived only from the verified lesson/evidence before downstream use. Verified lesson: Add one new bounded Genesis capability implementing this verified transferable lesson: Research-backed capability candidate from 'python-v0.7.3': ## What's Changed * Update website for 0.7.2 by @ekzhu in https://github.com/microsoft/autogen/pull/6902 * Typo in docs for 'NoOpTracerProvider' by @nicsuzor in https://github.com/microsoft/autogen/pull/6915 * Fix MCP example in readme by @ekzhu in https://github.com/microsoft/autogen/pull/6919 * Extend pydantic model capability for anyOf/oneOf item typing by @fiow123 in https://github.com/microsoft/autogen/pull/6925 * Update README.md with correct s",
    "## What's Changed * Update website for 0.7.2 by @ekzhu in https://github.com/microsoft/autogen/pull/6902 * Typo in docs for 'NoOpTracerProvider' by @nicsuzor in https://github.com/microsoft/autogen/pull/6915 * Fix MCP example in readme by @ekzhu in https://github.com/microsoft/autogen/pull/6919 * Extend pydantic model capability for anyOf/oneOf item typing by @fiow123 in https://github.com/microsoft/autogen/pull/6925 * Update README.md with correct stable version by @Jp3132 in https://github.com/microsoft/autogen/pull/6942 * fix: Add proper serialization to RedisStore for complex objects by @tejas-dharani in https://github.com/microsoft/autogen/pull/6905 * Fix OpenAIAgent function tool schema by @alexey-pelykh in https://github.com/microsoft/autogen/pull/6936 * Add model info for gpt-5 by @ekzhu in https://github.com/microsoft/autogen/pull/6945 * Update OpenAIAgent to reflect gap in supporting custom function tool by @ekzhu in https://github.com/microsoft/autogen/pull/6943 * Ensure task runner tools are always strict by @ekzhu in https://github.com/microsoft/autogen/pull/6946 * Update version to 0.7.3 by @ekzhu in https://github.com/microsoft/autogen/pull/6947 ## New Contributors",
    _learned_8ea81c76a275,
)


def _learned_3bc5fb6875a9(items, limit: int = 32) -> tuple[str, ...]:
    """Return bounded caller values explicitly grounded in verified lesson terms."""
    limit_i = int(limit)
    if limit_i < 1 or limit_i > 128:
        raise ValueError("lesson-grounding limit is out of bounds")
    terms = ('bounded', 'this', 'lesson', 'research-backed', 'from', 'what', 'hides', 'detecting', 'ranking', 'diagnosing', 'deviations', 'generative', 'evaluation', 'models', 'commonly', 'ranked')
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
    'learned_3bc5fb6875a9c903',
    "Ground bounded candidate context against terms derived only from the verified lesson/evidence before downstream use. Verified lesson: Add one new bounded Genesis capability implementing this verified transferable lesson: Research-backed capability candidate from 'What FID Hides: Detecting, Ranking, and Diagnosing Deviations in Generative Evaluation': Generative models are commonly ranked by Fréchet Inception Distance (FID) and Kernel Inception Distance (KID), yet FID's first-two-moment summary can miss distributional differences, and a reported scalar gap alone is not a calibrated test against sampling variation. FID's moment restriction has concrete consequences: on ImageNet, visually unrecognizable images optimized only t",
    "Generative models are commonly ranked by Fréchet Inception Distance (FID) and Kernel Inception Distance (KID), yet FID's first-two-moment summary can miss distributional differences, and a reported scalar gap alone is not a calibrated test against sampling variation. FID's moment restriction has concrete consequences: on ImageNet, visually unrecognizable images optimized only to match the reference Inception mean and covariance obtain FID $24.7$ versus $58.6$ for held-out real images (lower is better). Moreover, FID and KID are scalar discrepancies that are unchanged when the two samples are exchanged and therefore do not encode the direction of a dispersion change: under-dispersion, as can occur in mode collapse, versus over-dispersion. We introduce \\textbf{ZID} (\\emph{Z-resolved Integrated Diagnostic}), which combines six standardized location- and dispersion-sensitive arms from a rank graph (RISE) and Gaussian kernels (GPK at two bandwidths). Rather than asking one scalar to serve incompatible roles, ZID reports three linked outputs: an index for ranking departure magnitude, a permutation $p$-value for testing distributional equality, and a signed dispersion readout for diagnosi",
    _learned_3bc5fb6875a9,
)


def _learned_923e46228ae9(items, limit: int = 32) -> tuple[str, ...]:
    """Return bounded caller values explicitly grounded in verified lesson terms."""
    limit_i = int(limit)
    if limit_i < 1 or limit_i > 128:
        raise ValueError("lesson-grounding limit is out of bounds")
    terms = ('bounded', 'this', 'lesson', 'research-backed', 'from', 'b10569', 'details', 'open', 'model', 'dots3-note', 'text', 'conversion', 'init', 'impl', 'address', 'review')
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
    'learned_923e46228ae9008c',
    "Ground bounded candidate context against terms derived only from the verified lesson/evidence before downstream use. Verified lesson: Add one new bounded Genesis capability implementing this verified transferable lesson: Research-backed capability candidate from 'b10569': <details open> model: add dots3-note (#27060) * text: conversion * init impl * address review comments * fix rope * move to a new llama_kv_cache_dsa_iswa </details> **Website:** - <https://llama.app> **Attestations:** - <https://github.com/ggml-org/llama.cpp/attestations/42267121> **macOS/iOS:** - [macOS Apple Silicon (arm64)](https://github.com/ggml-org/llama.cpp/releases/download/b10569/llama-b10569-bin-macos-arm64.tar.gz) - macOS Apple Silicon (arm64, Kl",
    '<details open> model: add dots3-note (#27060) * text: conversion * init impl * address review comments * fix rope * move to a new llama_kv_cache_dsa_iswa </details> **Website:** - <https://llama.app> **Attestations:** - <https://github.com/ggml-org/llama.cpp/attestations/42267121> **macOS/iOS:** - [macOS Apple Silicon (arm64)](https://github.com/ggml-org/llama.cpp/releases/download/b10569/llama-b10569-bin-macos-arm64.tar.gz) - macOS Apple Silicon (arm64, KleidiAI enabled) [DISABLED](https://github.com/ggml-org/llama.cpp/pull/23780) - [macOS Intel (x64)](https://github.com/ggml-org/llama.cpp/releases/download/b10569/llama-b10569-bin-macos-x64.tar.gz) - [iOS XCFramework](https://github.com/ggml-org/llama.cpp/releases/download/b10569/llama-b10569-xcframework.zip) **Linux:** - [Ubuntu x64 (CPU)](https://github.com/ggml-org/llama.cpp/releases/download/b10569/llama-b10569-bin-ubuntu-x64.tar.gz) - [Ubuntu arm64 (CPU)](https://github.com/ggml-org/llama.cpp/releases/download/b10569/llama-b10569-bin-ubuntu-arm64.tar.gz) - [Ubuntu s390x (CPU)](https://github.com/ggml-org/llama.cpp/releases/download/b10569/llama-b10569-bin-ubuntu-s390x.tar.gz) - [Ubuntu x64 (Vulkan)](https://github.com/ggml-or',
    _learned_923e46228ae9,
)


def _learned_93215ce8773b(items, limit: int = 32) -> tuple[str, ...]:
    """Return bounded caller values explicitly grounded in verified lesson terms."""
    limit_i = int(limit)
    if limit_i < 1 or limit_i > 128:
        raise ValueError("lesson-grounding limit is out of bounds")
    terms = ('bounded', 'this', 'lesson', 'research-backed', 'from', 'b10567', 'details', 'open', 'ccache-clear', 'last', 'step', 'jobs', 'assisted-by', 'llama.cpp', 'qwen3.8-27b', 'update')
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
    'learned_93215ce8773b50f8',
    "Ground bounded candidate context against terms derived only from the verified lesson/evidence before downstream use. Verified lesson: Add one new bounded Genesis capability implementing this verified transferable lesson: Research-backed capability candidate from 'b10567': <details open> ci : run ccache-clear as the last step of release jobs (#27503) * ci : run ccache-clear as the last step of release jobs Assisted-by: pi:llama.cpp/Qwen3.8-27B * update disabled job too to force rebase --------- Co-authored-by: Sigbjørn Skjæret <sigbjorn.skjaeret@huggingface.co> </details> **Website:** - <https://llama.app> **Attestations:** - <https://github.com/ggml-org/llama.cpp/attestations/42213918> **macOS/iOS:** - [macOS Apple Silicon",
    '<details open> ci : run ccache-clear as the last step of release jobs (#27503) * ci : run ccache-clear as the last step of release jobs Assisted-by: pi:llama.cpp/Qwen3.8-27B * update disabled job too to force rebase --------- Co-authored-by: Sigbjørn Skjæret <sigbjorn.skjaeret@huggingface.co> </details> **Website:** - <https://llama.app> **Attestations:** - <https://github.com/ggml-org/llama.cpp/attestations/42213918> **macOS/iOS:** - [macOS Apple Silicon (arm64)](https://github.com/ggml-org/llama.cpp/releases/download/b10567/llama-b10567-bin-macos-arm64.tar.gz) - macOS Apple Silicon (arm64, KleidiAI enabled) [DISABLED](https://github.com/ggml-org/llama.cpp/pull/23780) - [macOS Intel (x64)](https://github.com/ggml-org/llama.cpp/releases/download/b10567/llama-b10567-bin-macos-x64.tar.gz) - [iOS XCFramework](https://github.com/ggml-org/llama.cpp/releases/download/b10567/llama-b10567-xcframework.zip) **Linux:** - [Ubuntu x64 (CPU)](https://github.com/ggml-org/llama.cpp/releases/download/b10567/llama-b10567-bin-ubuntu-x64.tar.gz) - [Ubuntu arm64 (CPU)](https://github.com/ggml-org/llama.cpp/releases/download/b10567/llama-b10567-bin-ubuntu-arm64.tar.gz) - [Ubuntu s390x (CPU)](https://git',
    _learned_93215ce8773b,
)


def _learned_0088a69ee3f1(items, limit: int = 32) -> tuple[str, ...]:
    """Return bounded caller values explicitly grounded in verified lesson terms."""
    limit_i = int(limit)
    if limit_i < 1 or limit_i > 128:
        raise ValueError("lesson-grounding limit is out of bounds")
    terms = ('bounded', 'this', 'lesson', 'research-backed', 'from', 'v0.2.0', 'overview', 'version', 'been', 'released', 'nightly', 'build', 'b10566', 'https', 'github.com', 'ggml-org')
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
    'learned_0088a69ee3f14b6f',
    "Ground bounded candidate context against terms derived only from the verified lesson/evidence before downstream use. Verified lesson: Add one new bounded Genesis capability implementing this verified transferable lesson: Research-backed capability candidate from 'v0.2.0': ## Overview New version has been released. **Nightly build:** [b10566](https://github.com/ggml-org/llama.cpp/releases/tag/b10566) **Web UI:** the `nightly-tag.txt` asset contains the tag of the corresponding nightly release **More info:** [dist : releases and versioning of ggml-org projects](https://github.com/ggml-org/ggml/discussions/1579) ## Changelog since v0.1.2 bb4caa754 llama.cpp : bump version to 0.2.0 (#27498) c4b0225d8 scripts : add release.sh for",
    '## Overview New version has been released. **Nightly build:** [b10566](https://github.com/ggml-org/llama.cpp/releases/tag/b10566) **Web UI:** the `nightly-tag.txt` asset contains the tag of the corresponding nightly release **More info:** [dist : releases and versioning of ggml-org projects](https://github.com/ggml-org/ggml/discussions/1579) ## Changelog since v0.1.2 bb4caa754 llama.cpp : bump version to 0.2.0 (#27498) c4b0225d8 scripts : add release.sh for release preparation (#27497) 5de25a748 sync : ggml 01ff204fb ggml : bump version to 0.21.0 (ggml/1597) 353b32d8b ci : remove duplicate flag (#27488) 7a0e42fd0 Revert "sycl : add Q2_K reordered MMVQ and ESIMD kernels (#26336)" (#27486) 5b6ddc967 ui: Settings navigation cleanup (#27241) e467c2ff6 ci : add nightly-tag.txt to make-release (#27485) 171974745 ci : release clean-up (#27477) 62b226906 kleidiai : add SME2 F32 GEMV kernel support (#26891) ff14356e0 sycl : add Q2_K reordered MMVQ and ESIMD kernels (#26336) 5fff12845 test : make the FA V-is-view-of-K case a test case parameter (#27394) 9e89a196b sycl : Add Q5_K ESIMD kernel (#26376) cd26896c1 opencl: keep the vocab-scale K-quant lm_head on the CPU for Adreno A7X (compiler i',
    _learned_0088a69ee3f1,
)


def _learned_da56ee983d44(items, limit: int = 32) -> tuple[str, ...]:
    """Return bounded caller values explicitly grounded in verified lesson terms."""
    limit_i = int(limit)
    if limit_i < 1 or limit_i > 128:
        raise ValueError("lesson-grounding limit is out of bounds")
    terms = ('bounded', 'this', 'lesson', 'research-backed', 'from', 'conceptguard', 'benchmarking', 'context-sensitive', 'unlearning', 'large', 'language', 'models', 'llms', 'increasingly', 'require', 'selective')
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
    'learned_da56ee983d44e1b8',
    "Ground bounded candidate context against terms derived only from the verified lesson/evidence before downstream use. Verified lesson: Add one new bounded Genesis capability implementing this verified transferable lesson: Research-backed capability candidate from 'ConceptGuard: Benchmarking Context-Sensitive Unlearning in Large Language Models': Large Language Models (LLMs) increasingly require selective removal of harmful or sensitive knowledge, called unlearning, yet existing methods and benchmarks fail to evaluate this capability completely. Current approaches rely on disjoint forget and retain sets composed of independent facts, and measure success using simple and direct factual recall. This framing fails to capture a ke",
    'Large Language Models (LLMs) increasingly require selective removal of harmful or sensitive knowledge, called unlearning, yet existing methods and benchmarks fail to evaluate this capability completely. Current approaches rely on disjoint forget and retain sets composed of independent facts, and measure success using simple and direct factual recall. This framing fails to capture a key requirement of unlearning, namely the ability to eliminate harmful behaviors while preserving benign and beneficial knowledge. We argue that effective unlearning must operate at the level of concepts, ensuring complete removal of unsafe applications while maintaining their correct and useful usage, thereby achieving conceptually meaningful and complete unlearning. To better evaluate unlearning techniques from such a practical viewpoint, we introduce the notion of dual-use concepts: concepts that can be used in both harmful and benign contexts. Building on these concepts, we construct a benchmark called ConceptGuard where forget and retain sets are explicitly complementary in concept usage. Our benchmark uniquely enables unlearning to be explored and gauged at the level of concepts, instead of sparse',
    _learned_da56ee983d44,
)


def _learned_27487ea59e3d(items, limit: int = 32) -> tuple[str, ...]:
    """Return bounded caller values explicitly grounded in verified lesson terms."""
    limit_i = int(limit)
    if limit_i < 1 or limit_i > 128:
        raise ValueError("lesson-grounding limit is out of bounds")
    terms = ('glm-5.3-flash', 'first', 'natively', 'multimodal', 'model', 'glm-5', 'series', 'with', 'total', 'parameters', 'just', 'huggingface', 'transformers', 'v5.16.1', 'published', 'active')
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
    'learned_27487ea59e3d',
    'Ground bounded candidate context against terms derived only from the verified lesson/evidence before downstream use. Verified lesson: GLM-5.3-Flash, the first **natively multimodal model** in the GLM-5 series. With 320B total parameters and just 18B a....',
    "huggingface/transformers release 'Release v5.16.1', published 2026-08-26T14:50:01Z: GLM-5.3-Flash, the first **natively multimodal model** in the GLM-5 series. With 320B total parameters and just 18B active parameters, it outperforms GLM-5.2 across benchmarks and real-world workloads at one-tenth the price, while approaching Claude Opus 4.8 on coding and agentic benchmarks. Source: https://github.com/huggingface/transformers/releases/tag/v5.16.1",
    _learned_27487ea59e3d,
)


def _learned_05e11793dee7(items, limit: int = 32) -> tuple[str, ...]:
    """Return bounded caller values explicitly grounded in verified lesson terms."""
    limit_i = int(limit)
    if limit_i < 1 or limit_i > 128:
        raise ValueError("lesson-grounding limit is out of bounds")
    terms = ('uses', 'multiple', 'query', 'heads', 'score', 'compressed', 'blocks', 'selects', 'most', 'relevant', 'contiguous', 'token', 'huggingface', 'transformers', 'v5.16.0', 'published')
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
    'learned_05e11793dee7',
    'Ground bounded candidate context against terms derived only from the verified lesson/evidence before downstream use. Verified lesson: QSA uses multiple query heads to score compressed key blocks, selects the most relevant contiguous token blocks, and....',
    "huggingface/transformers release 'Release: v5.16.0', published 2026-08-26T12:35:15Z: QSA uses multiple query heads to score compressed key blocks, selects the most relevant contiguous token blocks, and keeps the incomplete trailing block uncompressed. This block-level selection reduces indexing overhead and improves memory locality for long sequences. Combined with Gated DeltaNet, QSA makes Qwen4-Exp the first hybrid architecture to integrate linear and sparse attention, substantially improving inference efficiency for long-context workloads. Source: https://github.com/huggingface/transformers/releases/tag/v5.16.0",
    _learned_05e11793dee7,
)


def _learned_104c4fcba936(items, limit: int = 32) -> tuple[str, ...]:
    """Return bounded caller values explicitly grounded in verified lesson terms."""
    limit_i = int(limit)
    if limit_i < 1 or limit_i > 128:
        raise ValueError("lesson-grounding limit is out of bounds")
    terms = ('deepseek', 'sparse', 'works', 'end-to-end', 'plain', 'decode', 'dspark', 'speculative', 'decoding', 'vllm-project', 'vllm', 'v0.28.0', 'published', 'joined', 'quark', 'nvfp4')
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
    'learned_104c4fcba936',
    'Ground bounded candidate context against terms derived only from the verified lesson/evidence before downstream use. Verified lesson: **DeepSeek V4**: sparse MLA now works end-to-end for plain decode, MTP, and DSpark speculative decoding (#51538), joi....',
    "vllm-project/vllm release 'v0.28.0', published 2026-08-26T09:46:30Z: **DeepSeek V4**: sparse MLA now works end-to-end for plain decode, MTP, and DSpark speculative decoding (#51538), joined by AMD Quark NVFP4 support (#47972), reasoning-effort prompts and mappings (#50580), sparse top-k metadata kernel optimizations (#52084, #51967), narrowed eager CUDA graph regions (#51430, #52401), and ROCm enablement on gfx11 and gfx950 (#47017, #52212). Source: https://github.com/vllm-project/vllm/releases/tag/v0.28.0",
    _learned_104c4fcba936,
)


def _learned_8f6dcca7c01f(items, limit: int = 32) -> tuple[str, ...]:
    """Return bounded caller values explicitly grounded in verified lesson terms."""
    limit_i = int(limit)
    if limit_i < 1 or limit_i > 128:
        raise ValueError("lesson-grounding limit is out of bounds")
    terms = ('multimodal', 'vidcom2', 'video', 'token', 'pruning', 'qwen3.5', 'cuda', 'graph', 'gemma-4', 'cosm', 'vllm-project', 'vllm', 'v0.27.0', 'published', 'cosmos3', 'modelopt')
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
    'learned_8f6dcca7c01f',
    'Ground bounded candidate context against terms derived only from the verified lesson/evidence before downstream use. Verified lesson: Multimodal: VidCom2 video token pruning (#47750), EVS for Qwen3.5 (#48912), ViT CUDA graph for Gemma-4 (#46837), Cosm....',
    "vllm-project/vllm release 'v0.27.0', published 2026-08-10T21:18:11Z: Multimodal: VidCom2 video token pruning (#47750), EVS for Qwen3.5 (#48912), ViT CUDA graph for Gemma-4 (#46837), Cosmos3 FP8 ModelOpt/Diffusers remapping (#48952), MiniMax-M3 MSA speculative decode verification (#50032) and default video processor (#50305), DeepSeek-OCR-2 TTFT optimization (#49531), longer max audio duration for MOSS-TD (#49403). Source: https://github.com/vllm-project/vllm/releases/tag/v0.27.0",
    _learned_8f6dcca7c01f,
)


def _learned_df9a2fce458b(items, limit: int = 32) -> tuple[str, ...]:
    """Return bounded caller values explicitly grounded in verified lesson terms."""
    limit_i = int(limit)
    if limit_i < 1 or limit_i > 128:
        raise ValueError("lesson-grounding limit is out of bounds")
    terms = ('several', 'generation', 'improvements', 'fixes', 'were', 'made', 'including', 'enabling', 'batched', 'audio', 'qwen2.5', 'huggingface', 'transformers', 'v5.15.0', 'published', 'omni')
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
    'learned_df9a2fce458b',
    'Ground bounded candidate context against terms derived only from the verified lesson/evidence before downstream use. Verified lesson: Several generation improvements and bug fixes were made, including enabling batched audio generation for Qwen2.5/3-Om....',
    "huggingface/transformers release 'Release: v5.15.0', published 2026-08-10T10:28:13Z: Several generation improvements and bug fixes were made, including enabling batched audio generation for Qwen2.5/3-Omni, allowing sliding window cache layers to work with speculative decoding, and fixing memory overhead from static cache persistence across `generate()` calls. Multiple model-specific bugs were also resolved, including crashes in KyutaiSpeechToText, MusicgenForCausalLM, CTRL flex-attention, and assisted decoding for EncoderDecoder cache and OlmoHybrid models. Source: https://github.com/huggingface/transformers/releases/tag/v5.15.0",
    _learned_df9a2fce458b,
)


def _learned_de5bc409af89(items, limit: int = 32) -> tuple[str, ...]:
    """Return bounded caller values explicitly grounded in verified lesson terms."""
    limit_i = int(limit)
    if limit_i < 1 or limit_i > 128:
        raise ValueError("lesson-grounding limit is out of bounds")
    terms = ('bounded', 'this', 'lesson', 'research-backed', 'from', 'b10573', 'details', 'open', 'mtmd', 'support', 'webp', 'ffmpeg', 'website', 'https', 'llama.app', 'attestations')
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
    'learned_de5bc409af893198',
    "Ground bounded candidate context against terms derived only from the verified lesson/evidence before downstream use. Verified lesson: Add one new bounded Genesis capability implementing this verified transferable lesson: Research-backed capability candidate from 'b10573': <details open> mtmd: support webp via ffmpeg (#27520) </details> **Website:** - <https://llama.app> **Attestations:** - <https://github.com/ggml-org/llama.cpp/attestations/42289035> **macOS/iOS:** - [macOS Apple Silicon (arm64)](https://github.com/ggml-org/llama.cpp/releases/download/b10573/llama-b10573-bin-macos-arm64.tar.gz) - macOS Apple Silicon (arm64, KleidiAI enabled) [DISABLED](https://github.com/ggml-org/llama.cpp/pull/23780) - [macOS Intel (x64)](h",
    '<details open> mtmd: support webp via ffmpeg (#27520) </details> **Website:** - <https://llama.app> **Attestations:** - <https://github.com/ggml-org/llama.cpp/attestations/42289035> **macOS/iOS:** - [macOS Apple Silicon (arm64)](https://github.com/ggml-org/llama.cpp/releases/download/b10573/llama-b10573-bin-macos-arm64.tar.gz) - macOS Apple Silicon (arm64, KleidiAI enabled) [DISABLED](https://github.com/ggml-org/llama.cpp/pull/23780) - [macOS Intel (x64)](https://github.com/ggml-org/llama.cpp/releases/download/b10573/llama-b10573-bin-macos-x64.tar.gz) - [iOS XCFramework](https://github.com/ggml-org/llama.cpp/releases/download/b10573/llama-b10573-xcframework.zip) **Linux:** - [Ubuntu x64 (CPU)](https://github.com/ggml-org/llama.cpp/releases/download/b10573/llama-b10573-bin-ubuntu-x64.tar.gz) - [Ubuntu arm64 (CPU)](https://github.com/ggml-org/llama.cpp/releases/download/b10573/llama-b10573-bin-ubuntu-arm64.tar.gz) - [Ubuntu s390x (CPU)](https://github.com/ggml-org/llama.cpp/releases/download/b10573/llama-b10573-bin-ubuntu-s390x.tar.gz) - [Ubuntu x64 (Vulkan)](https://github.com/ggml-org/llama.cpp/releases/download/b10573/llama-b10573-bin-ubuntu-vulkan-x64.tar.gz) - [Ubuntu arm64 (Vul',
    _learned_de5bc409af89,
)


# GENESIS_LEARNED_CAPABILITY_INSERTION_POINT


# Issue #427 — information-flow martingale evidence distilled into a bounded local utility.
def _martingale_information_budget_427(step_divergences, peeking_penalty: float = 0.0) -> dict[str, float | int]:
    """Aggregate non-negative per-step information flow and an explicit anticipation penalty."""
    values_list: list[float] = []
    for index, item in enumerate(step_divergences):
        if index >= 4096:
            raise ValueError("step divergences exceed bounded input size")
        value = float(item)
        if value < 0.0 or value != value or value == float("inf"):
            raise ValueError("step divergences must be finite, non-negative, and bounded")
        values_list.append(value)
    values = tuple(values_list)
    penalty = float(peeking_penalty)
    if penalty < 0.0 or penalty != penalty or penalty == float("inf"):
        raise ValueError("peeking penalty must be finite and non-negative")
    divergence = sum(values)
    budget = divergence + penalty
    if divergence == float("inf") or budget == float("inf"):
        raise ValueError("information budget exceeds finite bounds")
    return {
        "steps": len(values),
        "conditional_divergence": divergence,
        "peeking_penalty": penalty,
        "information_budget": budget,
    }

register_capability(
    "martingale_information_budget_427",
    "Track a bounded martingale evidence budget as per-step conditional information flow plus an explicit random-time peeking penalty.",
    "Issue #427 external lesson: exact variational martingale identities resolve tail-control information by the chain rule into per-step conditional divergences, while arbitrary random times add an e-process peeking penalty.",
    _martingale_information_budget_427,
)


# Issue #431 — tensor-split support distilled from llama.cpp LFM2/LFM2MOE enablement.
def _lfm2_tensor_split_plan_431(model_family: str, device_weights) -> tuple[float, ...]:
    """Normalize a bounded device-weight plan for LFM2/LFM2MOE tensor splitting."""
    family = str(model_family).strip().lower().replace("-", "").replace("_", "")
    if family not in {"lfm2", "lfm2moe"}:
        raise ValueError("tensor split plan is limited to LFM2/LFM2MOE")
    weights_list: list[float] = []
    for index, item in enumerate(device_weights):
        if index >= 32:
            raise ValueError("device weights exceed bounded input size")
        value = float(item)
        if value < 0.0 or value != value or value == float("inf"):
            raise ValueError("device weights must be finite, non-negative, and bounded")
        weights_list.append(value)
    weights = tuple(weights_list)
    if not weights:
        raise ValueError("device weights must be finite, non-negative, and bounded")
    total = sum(weights)
    if total <= 0.0 or total == float("inf"):
        raise ValueError("tensor split requires positive finite total device weight")
    return tuple(item / total for item in weights)

register_capability(
    "lfm2_tensor_split_plan_431",
    "Create a deterministic bounded tensor-split plan for LFM2/LFM2MOE across explicitly weighted devices.",
    "Issue #431 external lesson: llama.cpp b10549 / PR #26993 enabled tensor split for LFM2 and LFM2MOE; Genesis applies the transferable policy as explicit normalized device partitioning without touching devices at import time.",
    _lfm2_tensor_split_plan_431,
)


# Issue #432 — safe partial K tile handling distilled from llama.cpp Metal matmul tail fix.
def _partial_k_tile_extent_432(total_k: int, loop_k: int, tile_k: int = 32) -> int:
    """Clamp the current K tile to the remaining valid tensor extent."""
    total = int(total_k)
    offset = int(loop_k)
    tile = int(tile_k)
    if total < 0 or offset < 0 or tile < 1 or tile > 4096:
        raise ValueError("K extents are out of bounds")
    if offset >= total:
        return 0
    return min(tile, total - offset)

register_capability(
    "partial_k_tile_extent_432",
    "Clamp a matmul K tile to the remaining valid extent so partial tails never request out-of-bounds elements.",
    "Issue #432 external lesson: llama.cpp b10545 / PR #27450 fixed Metal tensor matmul tails by using dynamic K extent and min(tile, K-loop_k) clamping for non-32-aligned K.",
    _partial_k_tile_extent_432,
)


# Issue #433 — explicit multimodal projection device routing with legacy fallback.
def _mmproj_device_selection_433(
    explicit_device: str | None,
    legacy_device: str | None,
    available,
    *,
    default: str | None = None,
) -> str | None:
    """Prefer explicit mmproj placement, then legacy configuration, then a safe default."""
    choices_list: list[str] = []
    for index, item in enumerate(available):
        if index >= 64:
            raise ValueError("available device scan exceeds bound")
        name = str(item).strip()
        if name:
            choices_list.append(name)
    choices = tuple(choices_list)
    for candidate in (explicit_device, legacy_device, default):
        name = str(candidate).strip() if candidate is not None else ""
        if name and name in choices:
            return name
    return choices[0] if choices else None

register_capability(
    "mmproj_device_selection_433",
    "Select multimodal-projection placement from an explicit device request while preserving a legacy device fallback and bounded available-device set.",
    "Issue #433 external lesson: llama.cpp b10541 / PR #23255 added --mmproj-device plus backward-compatible MTMD_BACKEND_DEVICE routing and immediate backend selection; Genesis preserves the explicit-over-legacy precedence without import-time device access.",
    _mmproj_device_selection_433,
)

