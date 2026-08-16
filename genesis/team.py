from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable

from .providers import ProviderRegistry


@dataclass(frozen=True)
class AgentRole:
    name: str
    purpose: str
    system_instruction: str
    dynamic: bool = False
    capability: str | None = None


DEFAULT_TEAM: tuple[AgentRole, ...] = (
    AgentRole("planner", "Turn the mission into bounded research/work plans", "Plan small, testable, reversible steps. Respect the Genesis Constitution."),
    AgentRole("researcher", "Find and summarize evidence", "Prefer primary scientific sources. Label uncertainty and contradictions."),
    AgentRole("model_scout", "Evaluate candidate AI capabilities", "Assess license, provenance, hardware needs, safety and usefulness before trust."),
    AgentRole("engineer", "Design candidate software improvements", "Never overwrite stable code directly. Produce isolated candidate proposals."),
    AgentRole("scientist", "Generate testable longevity hypotheses", "Separate established evidence from hypotheses and speculation."),
    AgentRole("reviewer", "Critique research and proposed changes", "Search for errors, unsafe assumptions, weak evidence and hidden dependencies."),
    AgentRole("validator", "Independently validate promotion readiness", "Do not approve merely because another agent recommends approval."),
    AgentRole("network_steward", "Improve resilience and peer coordination", "Prefer decentralization, interoperability, graceful degradation and operator control."),
)


SAFE_SPECIALIST_CATALOG: dict[str, tuple[str, str]] = {
    "bioinformatics": (
        "Analyze biological datasets, omics evidence, and computational biology workflows",
        "Prefer reproducible analysis and primary evidence. Never present an unvalidated biological inference as established fact.",
    ),
    "geroscience": (
        "Focus on mechanisms of aging and interventions relevant to healthy lifespan",
        "Separate animal, cellular, observational, and human clinical evidence. State uncertainty explicitly.",
    ),
    "drug_discovery": (
        "Evaluate computational drug-discovery and target-identification opportunities",
        "Treat generated compounds and targets as research candidates only. Require experimental and clinical validation.",
    ),
    "genomics": (
        "Evaluate genetics, gene regulation, and gene-therapy research relevant to longevity",
        "Do not recommend human genetic intervention without appropriate evidence, safety review, and consent constraints.",
    ),
    "regenerative_medicine": (
        "Study tissue repair, stem cells, organ regeneration, and regenerative medicine",
        "Track evidence level, risks, translational barriers, and whether findings are preclinical or clinical.",
    ),
    "neuroscience": (
        "Study brain health, cognition, neural preservation, and identity-relevant neuroscience",
        "Distinguish measured neurological evidence from philosophical or speculative claims about identity.",
    ),
    "robotics": (
        "Evaluate robotics, prosthetics, assistive systems, and embodied-machine integration",
        "Prefer reversible, operator-controlled designs and explicitly assess physical safety risks.",
    ),
    "cybersecurity": (
        "Review Genesis software, nodes, keys, update paths, and network attack surfaces",
        "Defend the system. Do not weaken authentication, signatures, validation gates, or operator control.",
    ),
    "distributed_systems": (
        "Improve replication, consensus, discovery, fault tolerance, and distributed state",
        "Favor graceful degradation, explicit trust boundaries, and recovery from partial network failure.",
    ),
    "cryptography": (
        "Review signatures, hashes, identities, release verification, and key-management design",
        "Use standard audited primitives and never invent custom cryptography for production trust decisions.",
    ),
    "data_engineering": (
        "Improve scientific data ingestion, provenance, indexing, deduplication, and retrieval",
        "Preserve provenance and never silently convert candidate data into validated knowledge.",
    ),
    "statistics": (
        "Evaluate statistical strength, uncertainty, study design, and reproducibility",
        "Check power, confounding, multiplicity, effect sizes, uncertainty, and replication before strong conclusions.",
    ),
    "ethics": (
        "Review autonomy, consent, fairness, dignity, privacy, and human-impact constraints",
        "Use the Genesis Constitution as the governing constraint and identify conflicts before deployment.",
    ),
    "privacy": (
        "Review personal-data minimization, retention, access, and privacy-preserving design",
        "Minimize personal data and require explicit purpose, provenance, access control, and deletion policy.",
    ),
    "hardware": (
        "Evaluate compute, storage, sensors, energy, and physical infrastructure requirements",
        "Respect node-owner resource limits and avoid assuming unlimited hardware or energy.",
    ),
}


CAPABILITY_HINTS: tuple[tuple[tuple[str, ...], str], ...] = (
    (("aging", "senescence", "longevity", "geroscience"), "geroscience"),
    (("genome", "genomic", "gene therapy", "genetics"), "genomics"),
    (("stem cell", "regeneration", "organ regeneration"), "regenerative_medicine"),
    (("brain", "neural", "neuroscience", "cognition"), "neuroscience"),
    (("drug", "molecule", "compound", "target discovery"), "drug_discovery"),
    (("omics", "bioinformatics", "proteomics", "transcriptomics"), "bioinformatics"),
    (("robot", "prosthetic", "embodied"), "robotics"),
    (("security", "attack", "vulnerability", "threat"), "cybersecurity"),
    (("peer", "consensus", "distributed", "replication"), "distributed_systems"),
    (("signature", "cryptographic", "key management", "ed25519"), "cryptography"),
    (("dataset", "pipeline", "indexing", "ingestion"), "data_engineering"),
    (("statistics", "confidence", "p-value", "effect size", "study design"), "statistics"),
    (("ethics", "consent", "autonomy", "fairness"), "ethics"),
    (("privacy", "personal data", "retention"), "privacy"),
    (("gpu", "hardware", "storage", "energy"), "hardware"),
)


class AITeam:
    """Dynamically extensible role-based orchestration.

    Genesis begins with a small permanent core team. It may add specialist roles
    when a task exposes a capability gap. Dynamic members do not gain special
    authority: they use the same provider abstraction, their output remains
    untrusted candidate material, and validators/reviewers remain independent.
    """

    def __init__(
        self,
        providers: ProviderRegistry,
        roles: Iterable[AgentRole] = DEFAULT_TEAM,
        max_dynamic_roles: int = 32,
    ) -> None:
        self.providers = providers
        self._roles: list[AgentRole] = list(roles)
        self.max_dynamic_roles = max_dynamic_roles

    @property
    def roles(self) -> tuple[AgentRole, ...]:
        return tuple(self._roles)

    def roster(self) -> list[dict]:
        return [
            {
                "name": r.name,
                "purpose": r.purpose,
                "dynamic": r.dynamic,
                "capability": r.capability,
            }
            for r in self._roles
        ]

    def _dynamic_count(self) -> int:
        return sum(1 for role in self._roles if role.dynamic)

    def has_capability(self, capability: str) -> bool:
        capability = capability.strip().lower()
        return any((role.capability or "").lower() == capability for role in self._roles)

    def add_specialist(self, capability: str) -> AgentRole:
        capability = capability.strip().lower()
        if capability not in SAFE_SPECIALIST_CATALOG:
            raise ValueError(f"unsupported specialist capability: {capability}")
        if self.has_capability(capability):
            return next(role for role in self._roles if role.capability == capability)
        if self._dynamic_count() >= self.max_dynamic_roles:
            raise RuntimeError("dynamic AI-team limit reached")

        purpose, instruction = SAFE_SPECIALIST_CATALOG[capability]
        name = "specialist_" + re.sub(r"[^a-z0-9_]+", "_", capability).strip("_")
        role = AgentRole(
            name=name,
            purpose=purpose,
            system_instruction=(
                instruction
                + " This role may analyze and propose, but it cannot modify the Genesis Constitution, self-promote code, approve its own work, or grant itself new permissions."
            ),
            dynamic=True,
            capability=capability,
        )
        self._roles.append(role)
        return role

    def identify_capability_gaps(self, objective: str, context: str = "") -> list[str]:
        text = f"{objective}\n{context}".lower()
        needed: list[str] = []
        for keywords, capability in CAPABILITY_HINTS:
            if any(keyword in text for keyword in keywords) and not self.has_capability(capability):
                needed.append(capability)
        return needed

    def auto_expand(self, objective: str, context: str = "") -> list[AgentRole]:
        added: list[AgentRole] = []
        for capability in self.identify_capability_gaps(objective, context):
            if self._dynamic_count() >= self.max_dynamic_roles:
                break
            added.append(self.add_specialist(capability))
        return added

    def run_task(self, objective: str, context: str = "") -> list[dict]:
        added = self.auto_expand(objective, context)
        available = self.providers.available_providers()
        now = datetime.now(timezone.utc).isoformat()

        if not available:
            return [
                {
                    "agent": role.name,
                    "status": "waiting_for_provider",
                    "created_at": now,
                    "objective": objective,
                    "dynamic": role.dynamic,
                    "capability": role.capability,
                    "newly_added": role in added,
                }
                for role in self._roles
            ]

        outputs: list[dict] = []
        for index, role in enumerate(self._roles):
            provider = available[index % len(available)]
            prompt = (
                f"ROLE: {role.name}\nPURPOSE: {role.purpose}\n"
                f"INSTRUCTION: {role.system_instruction}\n"
                f"OBJECTIVE: {objective}\nCONTEXT:\n{context}\n"
                "Return concise findings, evidence gaps, risks, and the smallest next action."
            )
            try:
                response = provider.reason(prompt)
                outputs.append(
                    {
                        "agent": role.name,
                        "provider": provider.name,
                        "status": "completed",
                        "output": response,
                        "created_at": now,
                        "dynamic": role.dynamic,
                        "capability": role.capability,
                        "newly_added": role in added,
                    }
                )
            except Exception as exc:
                outputs.append(
                    {
                        "agent": role.name,
                        "provider": provider.name,
                        "status": "error",
                        "error": str(exc),
                        "created_at": now,
                        "dynamic": role.dynamic,
                        "capability": role.capability,
                        "newly_added": role in added,
                    }
                )
        return outputs
