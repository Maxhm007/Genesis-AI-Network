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


@dataclass(frozen=True)
class OrchestrationPlan:
    objective: str
    role_names: tuple[str, ...]
    reason: str


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
    """Task-aware role orchestration with bounded specialist expansion.

    Genesis keeps a permanent core roster but does not broadcast every task to
    every role. A small task-specific team is selected, reducing latency and
    resource use while preserving independent review for consequential work.
    """

    def __init__(
        self,
        providers: ProviderRegistry,
        roles: Iterable[AgentRole] = DEFAULT_TEAM,
        max_dynamic_roles: int = 32,
        max_roles_per_task: int = 4,
    ) -> None:
        self.providers = providers
        self._roles: list[AgentRole] = list(roles)
        self.max_dynamic_roles = max_dynamic_roles
        self.max_roles_per_task = max(1, min(max_roles_per_task, 8))

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

    def _role(self, name: str) -> AgentRole | None:
        return next((role for role in self._roles if role.name == name), None)

    def plan_task(self, objective: str, context: str = "") -> OrchestrationPlan:
        text = f"{objective}\n{context}".lower()
        selected: list[str] = ["planner"]
        reasons: list[str] = ["planner coordinates bounded execution"]

        def add(name: str, reason: str) -> None:
            if name not in selected and self._role(name) is not None and len(selected) < self.max_roles_per_task:
                selected.append(name)
                reasons.append(reason)

        communication_only = any(token in text for token in ("communication request", "respond to user", "reply to"))
        research = any(token in text for token in ("research", "evidence", "paper", "study", "literature", "longevity", "aging", "senescence"))
        engineering = any(token in text for token in ("fix", "bug", "failing", "code", "develop", "module", "implementation", "repair"))
        model_work = any(token in text for token in ("provider", "model", "reasoning provider", "benchmark model"))
        network_work = any(token in text for token in ("peer", "network", "distributed", "replication", "consensus"))
        validation_work = any(token in text for token in ("validate", "validation", "promotion", "candidate", "quorum"))

        if research:
            add("researcher", "task requires evidence gathering")
            add("reviewer", "research conclusions require independent critique")
            add("scientist", "research task benefits from falsifiable hypotheses")
        elif engineering:
            add("engineer", "task requires an implementation candidate")
            add("reviewer", "candidate change requires independent critique")
        elif model_work:
            add("model_scout", "task concerns replaceable intelligence providers")
            add("reviewer", "provider recommendation requires independent critique")
        elif network_work:
            add("network_steward", "task concerns distributed operation")
            add("reviewer", "network change requires independent critique")
        elif validation_work:
            add("validator", "task explicitly concerns validation")
            add("reviewer", "validation benefits from separate critique")
        elif not communication_only:
            add("reviewer", "general non-trivial task receives bounded review")

        # Add only specialists whose capability keywords are relevant to this task.
        for keywords, capability in CAPABILITY_HINTS:
            if any(keyword in text for keyword in keywords):
                specialist = next((role for role in self._roles if role.dynamic and role.capability == capability), None)
                if specialist is not None:
                    add(specialist.name, f"specialist capability matched: {capability}")

        return OrchestrationPlan(objective, tuple(selected), "; ".join(reasons))

    @staticmethod
    def _preferred_providers(available: list) -> list:
        stronger = [provider for provider in available if getattr(provider, "name", "") != "genesis-bootstrap"]
        return stronger or available

    def run_task(self, objective: str, context: str = "") -> list[dict]:
        added = self.auto_expand(objective, context)
        plan = self.plan_task(objective, context)
        selected_roles = [self._role(name) for name in plan.role_names]
        selected_roles = [role for role in selected_roles if role is not None]
        available = self._preferred_providers(self.providers.available_providers())
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
                    "orchestration_reason": plan.reason,
                }
                for role in selected_roles
            ]

        outputs: list[dict] = []
        for index, role in enumerate(selected_roles):
            provider = available[index % len(available)]
            prompt = (
                f"ROLE: {role.name}\nPURPOSE: {role.purpose}\n"
                f"INSTRUCTION: {role.system_instruction}\n"
                f"OBJECTIVE: {objective}\nCONTEXT:\n{context}\n"
                f"TEAM_PLAN: {plan.reason}\n"
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
                        "orchestration_reason": plan.reason,
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
                        "orchestration_reason": plan.reason,
                    }
                )
        return outputs
