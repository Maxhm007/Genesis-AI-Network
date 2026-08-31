from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
import json

from .types import ModuleManifest


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class ModuleVersionRecord:
    module_id: str
    version: str
    manifest: dict
    benchmark_summary: dict
    created_at: str
    status: str = "validated"


class ModuleVersionManager:
    """Persist validated module manifests and choose safe rollback targets.

    This manager records version state only. Applying code/config changes still
    goes through Genesis candidate validation and promotion.
    """

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.write_text(json.dumps({"version": 1, "modules": {}}, indent=2), encoding="utf-8")

    def _load(self) -> dict:
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(payload.get("modules"), dict):
            raise ValueError("invalid module version store")
        return payload

    def _save(self, payload: dict) -> None:
        self.path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    def record_validated(self, manifest: ModuleManifest, benchmark_summary: dict | None = None) -> ModuleVersionRecord:
        record = ModuleVersionRecord(
            module_id=manifest.module_id,
            version=manifest.version,
            manifest=manifest.to_dict(),
            benchmark_summary=dict(benchmark_summary or {}),
            created_at=utc_now(),
        )
        payload = self._load()
        history = payload["modules"].setdefault(manifest.module_id, [])
        if history and history[-1].get("version") == manifest.version and history[-1].get("manifest") == record.manifest:
            return ModuleVersionRecord(**history[-1])
        history.append(asdict(record))
        self._save(payload)
        return record

    def history(self, module_id: str) -> list[ModuleVersionRecord]:
        payload = self._load()
        return [ModuleVersionRecord(**item) for item in payload["modules"].get(module_id, [])]

    def rollback_target(self, module_id: str, current_version: str) -> ModuleVersionRecord | None:
        history = self.history(module_id)
        candidates = [item for item in history if item.version != current_version and item.status == "validated"]
        return candidates[-1] if candidates else None

    @staticmethod
    def should_rollback(before_percent: float, after_percent: float, *, regression_tolerance: float = 0.0) -> bool:
        return after_percent > before_percent - regression_tolerance
