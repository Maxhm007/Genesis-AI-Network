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


def _learned_f92ab6ae15c7(
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
    'runtime_device_selection_f92ab6ae15c7',
    "Select an explicit supported runtime device while preserving a compatible fallback path. Verified lesson: Research-backed capability candidate from 'b10541': <details open> mtmd: add --mmproj-device argument (#23255) * feat: add --mmproj-device arg & backwards compatible MTMD_BACKEND_DEVICE env var * feat: load mmproj device backend immediately, add -mmdev shortflag * fix: its a pointer now get the name * clean up * gen docs * nits --------- Co-authored-by: Xuan Son Nguyen <son@huggingface.co> </details> **Website:** - <https://llama.app> **Attestations:** - <https://github.com/ggml-org/llama.cpp/attestations/42037857> **macOS/iOS:** - [macOS Apple Silicon (arm64)](https://github.com/ggml-org/llam",
    '<details open> mtmd: add --mmproj-device argument (#23255) * feat: add --mmproj-device arg & backwards compatible MTMD_BACKEND_DEVICE env var * feat: load mmproj device backend immediately, add -mmdev shortflag * fix: its a pointer now get the name * clean up * gen docs * nits --------- Co-authored-by: Xuan Son Nguyen <son@huggingface.co> </details> **Website:** - <https://llama.app> **Attestations:** - <https://github.com/ggml-org/llama.cpp/attestations/42037857> **macOS/iOS:** - [macOS Apple Silicon (arm64)](https://github.com/ggml-org/llama.cpp/releases/download/b10541/llama-b10541-bin-macos-arm64.tar.gz) - macOS Apple Silicon (arm64, KleidiAI enabled) [DISABLED](https://github.com/ggml-org/llama.cpp/pull/23780) - [macOS Intel (x64)](https://github.com/ggml-org/llama.cpp/releases/download/b10541/llama-b10541-bin-macos-x64.tar.gz) - [iOS XCFramework](https://github.com/ggml-org/llama.cpp/releases/download/b10541/llama-b10541-xcframework.zip) **Linux:** - [Ubuntu x64 (CPU)](https://github.com/ggml-org/llama.cpp/releases/download/b10541/llama-b10541-bin-ubuntu-x64.tar.gz) - [Ubuntu arm64 (CPU)](https://github.com/ggml-org/llama.cpp/releases/download/b10541/llama-b10541-bin-ubuntu-a',
    _learned_f92ab6ae15c7,
)


# GENESIS_LEARNED_CAPABILITY_INSERTION_POINT
