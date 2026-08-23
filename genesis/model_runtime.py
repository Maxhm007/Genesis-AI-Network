from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .model_lab import ModelLab


RUNTIME_EVIDENCE_TYPE = "runtime_artifact"
ALLOWED_CAPABILITIES = frozenset({"reasoning", "coding", "research", "planning", "review"})


@dataclass(frozen=True)
class ActiveModelRuntimeSpec:
    model_id: str
    provider_name: str
    endpoint: str
    artifact_path: Path
    manifest_path: Path
    manifest_sha256: str
    capabilities: tuple[str, ...]


def _inside(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def _loopback_http_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme == "http" and parsed.hostname in {"127.0.0.1", "localhost", "::1"} and bool(parsed.port)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _runtime_payload_spec(root: Path, model_id: str, payload: dict[str, Any]) -> ActiveModelRuntimeSpec | None:
    runtime_root = (root / "runtime" / "model_artifacts").resolve()
    artifact_raw = str(payload.get("artifact_path") or "").strip()
    manifest_raw = str(payload.get("manifest_path") or "").strip()
    manifest_sha256 = str(payload.get("manifest_sha256") or "").strip().lower()
    endpoint = str(payload.get("endpoint") or "").strip()
    if not artifact_raw or not manifest_raw or len(manifest_sha256) != 64 or not _loopback_http_url(endpoint):
        return None

    artifact_path = (root / artifact_raw).resolve()
    manifest_path = (root / manifest_raw).resolve()
    if not _inside(artifact_path, runtime_root) or not _inside(manifest_path, runtime_root):
        return None
    if not artifact_path.exists() or not manifest_path.is_file():
        return None
    try:
        if _sha256_file(manifest_path) != manifest_sha256:
            return None
    except OSError:
        return None

    raw_capabilities = payload.get("capabilities")
    if not isinstance(raw_capabilities, list):
        return None
    capabilities = tuple(
        sorted(
            {
                str(value).strip().lower()
                for value in raw_capabilities
                if str(value).strip().lower() in ALLOWED_CAPABILITIES
            }
        )
    )
    if not capabilities:
        return None

    provider_name = str(payload.get("provider_name") or model_id).strip()
    if not provider_name.startswith("genesis-model-"):
        return None

    return ActiveModelRuntimeSpec(
        model_id=model_id,
        provider_name=provider_name,
        endpoint=endpoint.rstrip("/"),
        artifact_path=artifact_path,
        manifest_path=manifest_path,
        manifest_sha256=manifest_sha256,
        capabilities=capabilities,
    )


def discover_active_model_runtimes(root: Path) -> list[ActiveModelRuntimeSpec]:
    """Return only active Genesis models with intact local runtime evidence.

    A Model Lab entry is not executable merely because it is planned or even
    validated. Runtime discovery requires the model to have reached ``active``
    through the existing benchmark-gated lifecycle, plus an explicit local
    artifact record whose manifest hash still matches. Endpoints are restricted
    to loopback HTTP so this bridge cannot silently turn a Model Lab record into
    a remote provider dependency.
    """
    root = Path(root).resolve()
    lab = ModelLab(root)
    result: list[ActiveModelRuntimeSpec] = []
    for model in lab.list():
        if model.state != "active":
            continue
        evidence = lab.evidence(model.model_id)
        if not any(row["evidence_type"] == "benchmark" for row in evidence):
            continue
        runtime_rows = [row for row in evidence if row["evidence_type"] == RUNTIME_EVIDENCE_TYPE]
        if not runtime_rows:
            continue
        payload = runtime_rows[-1].get("payload")
        if not isinstance(payload, dict):
            continue
        spec = _runtime_payload_spec(root, model.model_id, payload)
        if spec is not None:
            result.append(spec)
    result.sort(key=lambda item: (item.provider_name, item.model_id))
    return result


def runtime_spec_intact(spec: ActiveModelRuntimeSpec) -> bool:
    if not spec.artifact_path.exists() or not spec.manifest_path.is_file():
        return False
    try:
        return _sha256_file(spec.manifest_path) == spec.manifest_sha256
    except OSError:
        return False
