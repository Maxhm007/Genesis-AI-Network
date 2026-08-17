from __future__ import annotations

import json
from pathlib import Path

from .types import ModuleManifest


class ModuleRegistry:
    """Registry of Genesis modules and their declared boundaries.

    The canonical architecture exposes a smaller set of independently meaningful
    modules. Historical module IDs remain compatibility aliases so existing code
    can migrate without turning every internal component into a first-class
    architectural module.
    """

    def __init__(self) -> None:
        self._modules: dict[str, ModuleManifest] = {}
        self._aliases: dict[str, str] = {}

    def register(self, manifest: ModuleManifest) -> None:
        if not manifest.module_id.startswith("genesis."):
            raise ValueError("module_id must start with genesis.")
        self._modules[manifest.module_id] = manifest
        for alias in manifest.metadata.get("aliases", []) or []:
            alias = str(alias).strip()
            if not alias.startswith("genesis."):
                raise ValueError("module alias must start with genesis.")
            if alias != manifest.module_id:
                self._aliases[alias] = manifest.module_id

    def canonical_id(self, module_id: str) -> str:
        return self._aliases.get(module_id, module_id)

    def get(self, module_id: str) -> ModuleManifest | None:
        return self._modules.get(self.canonical_id(module_id))

    def all(self) -> tuple[ModuleManifest, ...]:
        return tuple(self._modules.values())

    def active(self) -> tuple[ModuleManifest, ...]:
        return tuple(m for m in self._modules.values() if m.status == "active")

    def aliases(self) -> dict[str, str]:
        return dict(self._aliases)

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
        config_root = Path(root) / "config"
        consolidated = config_root / "module_architecture.json"
        if consolidated.exists():
            registry.load_file(consolidated)
            return registry

        # Legacy fallback for repositories predating the consolidated
        # architecture. This remains intentionally supported for compatibility.
        registry.load_file(config_root / "modules.json")
        extension_dir = config_root / "modules.d"
        if extension_dir.exists():
            for path in sorted(extension_dir.glob("*.json")):
                registry.load_file(path)
        return registry

    def capability_owners(self, capability: str) -> list[str]:
        capability = capability.strip().lower()
        return [
            module.module_id
            for module in self.active()
            if capability in {value.lower() for value in module.capabilities}
        ]
