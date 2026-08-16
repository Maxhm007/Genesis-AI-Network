from __future__ import annotations

import json
from pathlib import Path

from .types import ModuleManifest


class ModuleRegistry:
    """Registry of Genesis modules and their declared boundaries."""

    def __init__(self) -> None:
        self._modules: dict[str, ModuleManifest] = {}

    def register(self, manifest: ModuleManifest) -> None:
        if not manifest.module_id.startswith("genesis."):
            raise ValueError("module_id must start with genesis.")
        self._modules[manifest.module_id] = manifest

    def get(self, module_id: str) -> ModuleManifest | None:
        return self._modules.get(module_id)

    def all(self) -> tuple[ModuleManifest, ...]:
        return tuple(self._modules.values())

    def active(self) -> tuple[ModuleManifest, ...]:
        return tuple(m for m in self._modules.values() if m.status == "active")

    def load_file(self, path: str | Path) -> None:
        path = Path(path)
        if not path.exists():
            return
        payload = json.loads(path.read_text(encoding="utf-8"))
        modules = payload.get("modules", [])
        if not isinstance(modules, list):
            raise ValueError("modules registry must contain a modules list")
        for item in modules:
            self.register(ModuleManifest(**item))

    @classmethod
    def from_default_config(cls, root: str | Path) -> "ModuleRegistry":
        registry = cls()
        registry.load_file(Path(root) / "config" / "modules.json")
        return registry

    def capability_owners(self, capability: str) -> list[str]:
        capability = capability.strip().lower()
        return [
            module.module_id
            for module in self.active()
            if capability in {value.lower() for value in module.capabilities}
        ]
