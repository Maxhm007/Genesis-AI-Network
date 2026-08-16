from __future__ import annotations

from pathlib import Path

from ..capabilities import CapabilityEvaluator
from ..providers import ProviderRegistry
from ..team import AITeam
from .manager import ModuleManager
from .registry import ModuleRegistry


class ModularGenesis:
    """Read-only operational facade over Genesis module structure.

    Structural changes are returned as candidate proposals. This facade never
    activates a proposal by itself; activation requires the existing validation
    and promotion path.
    """

    def __init__(self, root: Path, providers: ProviderRegistry | None = None) -> None:
        self.root = root.resolve()
        self.providers = providers or ProviderRegistry()
        self.team = AITeam(self.providers)
        self.registry = ModuleRegistry.from_default_config(self.root)
        self.manager = ModuleManager(self.registry)
        self.capabilities = CapabilityEvaluator(self.root, self.providers, self.team)

    def status(self) -> dict:
        report = self.capabilities.report()
        proposals = self.manager.proposals_from_report(report)
        return {
            "architecture": "GMIA",
            "module_count": len(self.registry.all()),
            "active_module_count": len(self.registry.active()),
            "modules": [manifest.to_dict() for manifest in self.registry.all()],
            "capability_summary": {
                "score": report["score"],
                "max_score": report["max_score"],
                "percent": report["percent"],
            },
            "priority_gaps": report["priority_gaps"],
            "module_change_proposals": [proposal.to_dict() for proposal in proposals],
            "rule": "Module changes remain candidates until independently validated and promoted.",
        }
