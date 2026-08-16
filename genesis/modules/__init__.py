"""Genesis Modular Intelligence Architecture (GMIA)."""

from .manager import ModuleManager
from .registry import ModuleRegistry
from .types import ModuleManifest, ModuleProposal

__all__ = ["ModuleManager", "ModuleRegistry", "ModuleManifest", "ModuleProposal"]
