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


# GENESIS_LEARNED_CAPABILITY_INSERTION_POINT
