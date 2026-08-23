from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from .coding import CodingModule


class DeterministicLearnedCapabilityProvider:
    """Build a small evidence-backed learned capability without an LLM.

    This provider is intentionally narrow. It only activates for grounded
    `genesis.evolution_learning` tasks targeting the learned-capability incubator
    and only when the verified source evidence matches one of the explicit,
    testable capability templates below. Unsupported lessons return ``None`` so
    Genesis can checkpoint for a stronger non-Qwen coding provider instead of
    fabricating an implementation.
    """

    name = "genesis-deterministic-capability-builder"
    TARGET = "genesis/learned_capabilities.py"
    MARKER = "# GENESIS_LEARNED_CAPABILITY_INSERTION_POINT"
    MAX_LESSON_BYTES = 600
    MAX_EVIDENCE_BYTES = 1_600

    def __init__(self, proposal: dict) -> None:
        self._proposal = proposal

    def available(self) -> bool:
        return True

    def reason(self, prompt: str) -> str:
        del prompt
        return json.dumps(self._proposal, sort_keys=True)

    @staticmethod
    def _bounded_text(value: object, limit: int) -> str:
        raw = str(value or "").encode("utf-8", errors="replace")[:limit]
        return raw.decode("utf-8", errors="ignore").strip()

    @staticmethod
    def _normalized_path(value: object) -> str:
        return str(value or "").replace("\\", "/").lstrip("./")

    @staticmethod
    def _token(value: object, lesson: str, evidence: str) -> str:
        candidate = re.sub(r"[^0-9a-f]", "", str(value or "").lower())
        if len(candidate) >= 12:
            return candidate[:12]
        return hashlib.sha256(f"{lesson}|{evidence}".encode("utf-8")).hexdigest()[:12]

    @classmethod
    def _render_template(cls, token: str, combined: str) -> tuple[str, str, str] | None:
        function_name = f"_learned_{token}"

        if (
            ("device mismatch" in combined or "device_map" in combined or "token device" in combined)
            and ("candidate" in combined or "dflash" in combined or "mtp" in combined)
        ):
            capability_name = f"runtime_device_alignment_{token}"
            handler = f'''def {function_name}(
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
'''
            description = "Align candidate/generated work to an available reference runtime device to avoid device-map mismatches."
            return capability_name, description, handler

        if "lanczos" in combined and "bicubic" in combined and (
            "cuda" in combined or "accelerator" in combined or "device" in combined
        ):
            capability_name = f"accelerator_resample_fallback_{token}"
            handler = f'''def {function_name}(requested: str, device: str | None) -> str:
    """Use a compatible image resampling fallback on accelerator devices."""
    method = str(requested).strip().lower()
    device_name = str(device or "").strip().lower()
    if method == "lanczos" and ("cuda" in device_name or "gpu" in device_name or "accelerator" in device_name):
        return "bicubic"
    return method
'''
            description = "Fallback from Lanczos to bicubic on accelerator devices when the requested filter is unsupported."
            return capability_name, description, handler

        if "mlp_layer_types" in combined and ("absent" in combined or "missing" in combined):
            capability_name = f"optional_sequence_default_{token}"
            handler = f'''def {function_name}(config, key: str = "mlp_layer_types", default=()) -> tuple[object, ...]:
    """Return a bounded tuple default when an optional sequence config is absent."""
    values = dict(config)
    current = values.get(str(key))
    if current is None:
        current = default
    result = tuple(current)
    if len(result) > 256:
        raise ValueError("optional sequence config exceeds bounded size")
    return result
'''
            description = "Preserve compatibility when an optional sequence configuration field is absent."
            return capability_name, description, handler

        if "mmproj-device" in combined or "--mmproj-device" in combined or (
            "device" in combined and "backend" in combined
        ):
            capability_name = f"runtime_device_selection_{token}"
            handler = f'''def {function_name}(
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
'''
            description = "Select an explicit supported runtime device while preserving a compatible fallback path."
            return capability_name, description, handler

        if "clamp" in combined and ("extent" in combined or "tile" in combined) and (
            "tensor" in combined or "kernel" in combined
        ):
            capability_name = f"bounded_tensor_extent_{token}"
            handler = f'''def {function_name}(total: int, offset: int, tile: int = 32) -> int:
    """Clamp a partial tensor tile to the remaining valid extent."""
    total_i = int(total)
    offset_i = int(offset)
    tile_i = int(tile)
    if total_i < 0 or offset_i < 0 or tile_i < 0:
        raise ValueError("tensor extent inputs must be non-negative")
    return max(0, min(tile_i, total_i - offset_i))
'''
            description = "Clamp a partial tensor tile to the remaining valid extent instead of reading past bounds."
            return capability_name, description, handler

        if "tensor split" in combined or "tensor splitting" in combined or (
            "tensor" in combined and "shard" in combined
        ):
            capability_name = f"balanced_tensor_split_{token}"
            handler = f'''def {function_name}(total: int, parts: int) -> tuple[int, ...]:
    """Split a non-negative tensor/work extent into balanced deterministic parts."""
    total_i = int(total)
    parts_i = int(parts)
    if total_i < 0 or parts_i < 1 or parts_i > 256:
        raise ValueError("tensor split inputs are out of bounds")
    base, extra = divmod(total_i, parts_i)
    return tuple(base + (1 if index < extra else 0) for index in range(parts_i))
'''
            description = "Split a bounded tensor/work extent deterministically across multiple execution parts."
            return capability_name, description, handler

        if "linear memory" in combined or ("redis" in combined and "memory" in combined):
            capability_name = f"bounded_linear_memory_{token}"
            handler = f'''def {function_name}(items, limit: int = 64) -> tuple[object, ...]:
    """Retain the newest bounded linear-memory window without external side effects."""
    limit_i = int(limit)
    if limit_i < 1 or limit_i > 1024:
        raise ValueError("linear memory limit is out of bounds")
    values = tuple(items)
    return values[-limit_i:]
'''
            description = "Maintain a bounded linear-memory window while preserving insertion order."
            return capability_name, description, handler

        if "tool use" in combined or "tool call" in combined or "tool affordance" in combined or "mcp skill" in combined:
            capability_name = f"bounded_tool_workflow_{token}"
            handler = f'''def {function_name}(steps, limit: int = 32) -> tuple[str, ...]:
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
'''
            description = "Normalize a bounded ordered tool workflow while preserving explicit tool-step intent."
            return capability_name, description, handler

        return None

    @classmethod
    def for_task(
        cls,
        root: Path,
        task,
        coding: CodingModule,
    ) -> DeterministicLearnedCapabilityProvider | None:
        payload = dict(getattr(task, "payload", {}) or {})
        if str(payload.get("source") or "") != "genesis.evolution_learning":
            return None
        if cls._normalized_path(payload.get("target_path")) != cls.TARGET:
            return None

        finding = dict(dict(payload.get("discovery") or {}).get("finding") or {})
        if finding.get("new_capability") is not True or finding.get("grounded") is not True:
            return None

        lesson = cls._bounded_text(finding.get("lesson") or finding.get("summary"), cls.MAX_LESSON_BYTES)
        evidence = cls._bounded_text(
            finding.get("lesson_evidence") or finding.get("learning_evidence"),
            cls.MAX_EVIDENCE_BYTES,
        )
        if not lesson or not evidence:
            return None

        learning = dict(payload.get("learning") or {})
        token = cls._token(learning.get("fingerprint"), lesson, evidence)
        combined = "\n".join(
            str(value or "").lower()
            for value in (
                lesson,
                evidence,
                finding.get("summary"),
                " ".join(str(item) for item in (finding.get("lesson_topics") or [])),
            )
        )
        rendered = cls._render_template(token, combined)
        if rendered is None:
            return None
        capability_name, template_description, handler = rendered

        target = (Path(root).resolve() / cls.TARGET).resolve()
        if not target.is_file():
            return None
        current = target.read_text(encoding="utf-8")
        if current.count(cls.MARKER) != 1:
            raise RuntimeError("learned capability insertion marker is missing or ambiguous")
        if f'"{capability_name}"' in current or f"'{capability_name}'" in current:
            return None

        function_name = f"_learned_{token}"
        capability_description = template_description + " Verified lesson: " + lesson
        registration = (
            handler
            + "\n"
            + "register_capability(\n"
            + f"    {capability_name!r},\n"
            + f"    {capability_description!r},\n"
            + f"    {evidence!r},\n"
            + f"    {function_name},\n"
            + ")\n"
        )
        updated = current.replace(cls.MARKER, registration + "\n\n" + cls.MARKER, 1)
        proposal = {
            "title": f"Add learned capability {capability_name}",
            "rationale": "Deterministic evidence-backed capability synthesis from a grounded Genesis learning task.",
            "files": {cls.TARGET: updated},
        }
        coding.validate_proposal(proposal, cls.name)
        return cls(proposal)
