from __future__ import annotations

import uuid
from dataclasses import replace
from pathlib import Path
from typing import Iterable

from .registry import ModuleRegistry
from .types import ModuleManifest, ModuleProposal


PROTECTED_MODULES = {
    "genesis.identity",
    "genesis.validation",
}

SAFE_ACTIONS = {"add", "modify", "split", "merge", "replace", "retire", "reactivate"}

SPECIALIST_TEMPLATES: dict[str, dict] = {
    "advanced_reasoning": {
        "module_id": "genesis.reasoning",
        "name": "Reasoning Module",
        "purpose": "Provide replaceable structured reasoning and planning capability.",
        "capabilities": ["advanced_reasoning", "planning"],
        "permissions": ["provider.use", "knowledge.read", "knowledge.propose"],
        "implementation": "genesis.providers",
    },
    "scientific_research": {
        "module_id": "genesis.research_specialist",
        "name": "Research Specialist Module",
        "purpose": "Improve scientific literature analysis and evidence synthesis.",
        "capabilities": ["scientific_research", "evidence_synthesis"],
        "permissions": ["network.read", "knowledge.read", "knowledge.propose"],
        "implementation": "genesis.research",
    },
    "distributed_operation": {
        "module_id": "genesis.network_optimizer",
        "name": "Network Optimizer Module",
        "purpose": "Improve peer coordination, redundancy and distributed operation.",
        "capabilities": ["distributed_operation", "peer_optimization"],
        "permissions": ["network.read", "network.propose", "metrics.read"],
        "implementation": "genesis.peers",
    },
    "security": {
        "module_id": "genesis.security_specialist",
        "name": "Security Specialist Module",
        "purpose": "Review Genesis attack surfaces, permissions and hardening opportunities.",
        "capabilities": ["security", "threat_review"],
        "permissions": ["audit.read", "code.read", "knowledge.propose"],
        "implementation": None,
    },
}


class ModuleManager:
    """Plan structural evolution without bypassing Genesis validation.

    The manager may propose adding, modifying, splitting, merging, replacing,
    retiring, or reactivating modules. Proposals are candidate state only.
    Activation remains a separate validated promotion action.
    """

    def __init__(self, registry: ModuleRegistry) -> None:
        self.registry = registry

    def propose_for_capability_gap(self, gap: dict) -> ModuleProposal | None:
        capability = str(gap.get("capability", "")).strip()
        template = SPECIALIST_TEMPLATES.get(capability)
        if not template:
            return None
        existing = self.registry.capability_owners(capability)
        action = "modify" if existing else "add"
        target = existing[0] if existing else template["module_id"]
        manifest = dict(template)
        manifest.update(
            {
                "version": "0.1.0",
                "dependencies": [],
                "status": "candidate",
                "dynamic": True,
                "mutable": True,
                "protected": False,
                "metadata": {"generated_from_capability_gap": capability},
            }
        )
        return ModuleProposal(
            proposal_id="module-" + uuid.uuid4().hex[:12],
            action=action,
            target_module_id=target,
            title=f"{action.title()} module capability: {capability}",
            rationale=(
                f"Genesis measured {capability} at {gap.get('score')} of "
                f"{gap.get('max_score')} and identified it as a priority gap."
            ),
            requested_by="genesis.capability",
            capability=capability,
            current_score=gap.get("score"),
            target_score=gap.get("max_score"),
            candidate_manifest=manifest,
        )

    def proposals_from_report(self, capability_report: dict, limit: int = 3) -> list[ModuleProposal]:
        proposals: list[ModuleProposal] = []
        for gap in capability_report.get("priority_gaps", []):
            proposal = self.propose_for_capability_gap(gap)
            if proposal is not None:
                proposals.append(proposal)
            if len(proposals) >= limit:
                break
        return proposals

    def validate_proposal(self, proposal: ModuleProposal) -> None:
        if proposal.action not in SAFE_ACTIONS:
            raise ValueError("unsupported module lifecycle action")
        if proposal.target_module_id in PROTECTED_MODULES and proposal.action in {"retire", "replace"}:
            raise ValueError("protected Genesis module cannot be retired or replaced")
        if proposal.action in {"add", "modify", "replace"}:
            candidate = ModuleManifest(**proposal.candidate_manifest)
            if candidate.protected:
                raise ValueError("dynamic proposals cannot create protected modules")
            forbidden = {"constitution.write", "identity.write", "validation.bypass", "permissions.grant"}
            if forbidden.intersection(candidate.permissions):
                raise ValueError("candidate module requests forbidden permissions")

    def activate_validated(self, proposal: ModuleProposal) -> ModuleManifest | None:
        """Apply a proposal only after an external validation gate has approved it."""
        self.validate_proposal(proposal)
        if proposal.status != "validated":
            raise ValueError("module proposal must be independently validated before activation")
        if proposal.action in {"add", "modify", "replace"}:
            manifest = ModuleManifest(**proposal.candidate_manifest)
            manifest = replace(manifest, status="active")
            self.registry.register(manifest)
            return manifest
        target = self.registry.get(proposal.target_module_id or "")
        if target is None:
            return None
        if proposal.action == "retire":
            target.status = "retired"
        elif proposal.action == "reactivate":
            target.status = "active"
        return target
