from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .gden import ContributionPolicy, EvolutionLedger, NodeIdentity, make_advertisement
from .identity import GeneIdentity
from .providers import ProviderRegistry
from .team import AITeam


@dataclass(frozen=True)
class ChildGeneSpec:
    logical_id: str
    role: str
    specialties: tuple[str, ...]
    strategy: str = "independent_evidence_first"
    provider_preferences: tuple[str, ...] = ()
    max_cpu_percent: int = 20
    max_memory_mb: int = 2048
    max_storage_mb: int = 4096


DEFAULT_CHILDREN = (
    ChildGeneSpec(
        logical_id="gene-node-2",
        role="explorer_researcher",
        specialties=("research", "model_discovery", "architecture", "experimentation"),
        strategy="breadth_first_exploration: search multiple approaches, compare evidence, favor novel high-leverage options, then reduce to one falsifiable next step",
        provider_preferences=("qwen3-0.6b-local", "qwen", "genesis-http"),
    ),
    ChildGeneSpec(
        logical_id="gene-node-3",
        role="engineer_challenger",
        specialties=("engineering", "repair", "review", "validation_challenge"),
        strategy="skeptical_engineering: begin from failure modes and measurable acceptance criteria, prefer simpler robust implementations, challenge unsupported assumptions",
        provider_preferences=("phi-4-mini-local", "deepseek-local", "qwen3-0.6b-local", "genesis-http"),
    ),
)


class _PreferredProviderView:
    """Provider view that prefers a node-specific model without making it mandatory."""

    def __init__(self, registry: ProviderRegistry, preferences: tuple[str, ...]) -> None:
        self.registry = registry
        self.preferences = tuple(value.lower() for value in preferences)

    def available_providers(self):
        providers = self.registry.available_providers()
        if not self.preferences:
            return providers

        def rank(provider) -> tuple[int, str]:
            name = str(getattr(provider, "name", "")).lower()
            for index, preferred in enumerate(self.preferences):
                if preferred in name or name in preferred:
                    return index, name
            return len(self.preferences), name

        return sorted(providers, key=rank)


class GeneFederation:
    """Authorized cooperative Gene federation for Nodes 1, 2 and 3.

    Child nodes inherit the same Constitution hash and Gene identity/plan but keep
    independent local identities, state directories, ledgers, strategy profiles
    and work products. They may propose, compete, challenge and synthesize
    improvements; they cannot promote source changes or create additional child
    nodes without an explicit authorized node spec.
    """

    def __init__(
        self,
        root: Path,
        providers: ProviderRegistry | None = None,
        children: tuple[ChildGeneSpec, ...] = DEFAULT_CHILDREN,
    ) -> None:
        self.root = root.resolve()
        self.providers = providers or ProviderRegistry()
        self.children = children
        self.identity = GeneIdentity.load(self.root)
        self.runtime_root = self.root / "runtime" / "grce"
        self.runtime_root.mkdir(parents=True, exist_ok=True)
        self.constitution_hash = hashlib.sha256((self.root / "GENESIS_CONSTITUTION.md").read_bytes()).hexdigest()

    def _child_root(self, spec: ChildGeneSpec) -> Path:
        return self.runtime_root / spec.logical_id

    def _identity(self, spec: ChildGeneSpec) -> NodeIdentity:
        return NodeIdentity.load_or_create(self._child_root(spec) / "identity.key")

    def _team(self, spec: ChildGeneSpec) -> AITeam:
        return AITeam(_PreferredProviderView(self.providers, spec.provider_preferences))

    def provision(self) -> list[dict[str, Any]]:
        provisioned: list[dict[str, Any]] = []
        for spec in self.children:
            child_root = self._child_root(spec)
            child_root.mkdir(parents=True, exist_ok=True)
            identity = self._identity(spec)
            policy = ContributionPolicy(
                max_cpu_percent=spec.max_cpu_percent,
                max_memory_mb=spec.max_memory_mb,
                max_storage_mb=spec.max_storage_mb,
                allow_research=True,
                allow_validation=True,
                allow_model_inference=True,
                allow_storage=True,
                allow_task_execution=True,
            )
            advertisement = make_advertisement(
                identity,
                self.constitution_hash,
                capabilities=list(spec.specialties),
                policy=policy,
                state_root=str(child_root),
            )
            manifest = {
                "logical_id": spec.logical_id,
                "node_id": identity.node_id,
                "role": spec.role,
                "specialties": list(spec.specialties),
                "strategy": spec.strategy,
                "provider_preferences": list(spec.provider_preferences),
                "gene_nickname": self.identity.nickname,
                "master_ai_objective": self.identity.master_ai_objective,
                "constitution_sha256": self.constitution_hash,
                "authorized_parent": "gene-node-1",
                "replication_policy": "authorized_specs_only",
                "advertisement": advertisement,
            }
            (child_root / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
            ledger = EvolutionLedger(child_root / "evolution_ledger.jsonl")
            if not ledger.entries():
                ledger.append(identity, "child_gene_provisioned", manifest)
            provisioned.append(manifest)
        return provisioned

    @staticmethod
    def _completed(outputs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [item for item in outputs if item.get("status") == "completed"]

    @staticmethod
    def _render(outputs: list[dict[str, Any]]) -> str:
        completed = GeneFederation._completed(outputs)
        if not completed:
            return "No provider-backed output was available. Record the task for a later cycle; do not fabricate a result."
        return "\n\n".join(
            f"[{item.get('agent','agent')}/{item.get('provider','unknown')}] {str(item.get('output',''))[:6000]}"
            for item in completed
        )

    def _node_context(self, spec: ChildGeneSpec) -> str:
        return (
            self.identity.context_text()
            + f"\nNODE: {spec.logical_id}; role={spec.role}; specialties={','.join(spec.specialties)}"
            + f"\nSTRATEGY: {spec.strategy}"
            + f"\nPROVIDER_PREFERENCES: {','.join(spec.provider_preferences) or 'none'}"
            + f"\nCONSTITUTION_SHA256: {self.constitution_hash}"
        )

    def cooperative_cycle(self, objective: str) -> dict[str, Any]:
        manifests = {item["logical_id"]: item for item in self.provision()}
        node2 = next(spec for spec in self.children if spec.logical_id == "gene-node-2")
        node3 = next(spec for spec in self.children if spec.logical_id == "gene-node-3")

        node2_team = self._team(node2)
        node3_team = self._team(node3)
        integrator_team = AITeam(self.providers)

        # Competition round: both nodes solve the same objective independently.
        node2_outputs = node2_team.run_task(
            "Act as Gene Node 2. Solve the objective independently using your assigned strategy. "
            "Produce evidence, alternatives, measurable acceptance criteria, risks, and one bounded candidate approach. "
            "Do not assume Node 3's answer and do not claim unmeasured capability.\nObjective: " + objective,
            context=self._node_context(node2),
        )
        node2_text = self._render(node2_outputs)

        node3_outputs = node3_team.run_task(
            "Act as Gene Node 3. Solve the objective independently using your assigned strategy. "
            "Produce an implementation-oriented answer with explicit failure modes, measurable acceptance criteria, risks, "
            "and one bounded candidate approach. Do not assume Node 2's answer and do not claim unmeasured capability.\nObjective: " + objective,
            context=self._node_context(node3),
        )
        node3_text = self._render(node3_outputs)

        # Cross-challenge round: each node attacks the other solution after independence is preserved.
        node2_review_outputs = node2_team.run_task(
            "Act as Gene Node 2 reviewing a competing solution from Node 3. Identify evidence gaps, missed alternatives, "
            "and conditions under which Node 3 should win. Give concrete tests that discriminate the two approaches.\nObjective: "
            + objective
            + "\nNode 2 original:\n"
            + node2_text
            + "\nNode 3 competing solution:\n"
            + node3_text,
            context=self._node_context(node2),
        )
        node2_review_text = self._render(node2_review_outputs)

        node3_review_outputs = node3_team.run_task(
            "Act as Gene Node 3 reviewing a competing solution from Node 2. Search for hidden failure modes, unsupported "
            "claims, complexity, security weaknesses and validation gaps. State conditions under which Node 2 should win, "
            "and give concrete tests that discriminate the approaches.\nObjective: "
            + objective
            + "\nNode 3 original:\n"
            + node3_text
            + "\nNode 2 competing solution:\n"
            + node2_text,
            context=self._node_context(node3),
        )
        node3_review_text = self._render(node3_review_outputs)

        integration_outputs = integrator_team.run_task(
            "Act as Gene Node 1, coordinator and evidence judge. You know Gene's identity and plan below. Compare the two "
            "independent solutions and their cross-reviews. Select Node 2, Node 3, or a clearly defined hybrid. Explain the "
            "selection using evidence quality, expected capability gain, validation cost, reversibility, resource cost, security, "
            "and contribution to validated development velocity. Preserve disagreements. Require normal candidate tests and "
            "independent validator quorum before promotion. Do not merge or activate code directly.\n"
            + self.identity.context_text()
            + "\nObjective: "
            + objective
            + "\nNode 2 solution:\n"
            + node2_text
            + "\nNode 3 solution:\n"
            + node3_text
            + "\nNode 2 review of Node 3:\n"
            + node2_review_text
            + "\nNode 3 review of Node 2:\n"
            + node3_review_text,
            context="role=coordinator_integrator_evidence_judge; selection=node2|node3|hybrid; promotion=independent_validator_quorum_required",
        )
        integration_text = self._render(integration_outputs)

        cycle_id = hashlib.sha256(
            f"{datetime.now(timezone.utc).isoformat()}|{objective}|{node2_text}|{node3_text}|{integration_text}".encode("utf-8")
        ).hexdigest()[:20]
        record = {
            "cycle_id": cycle_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "gene_identity": self.identity.public_payload(),
            "objective": objective,
            "nodes": manifests,
            "competition": {
                "node_2": {"role": node2.role, "strategy": node2.strategy, "provider_preferences": list(node2.provider_preferences), "outputs": node2_outputs},
                "node_3": {"role": node3.role, "strategy": node3.strategy, "provider_preferences": list(node3.provider_preferences), "outputs": node3_outputs},
                "node_2_review_of_node_3": node2_review_outputs,
                "node_3_review_of_node_2": node3_review_outputs,
            },
            "node_1": {"role": "coordinator_integrator_evidence_judge", "outputs": integration_outputs},
            "recommendation": integration_text,
            "promotion_rule": "candidate_only_until_tests_and_independent_validator_quorum",
            "replication_rule": "additional_nodes_require_explicit_authorized_spec",
        }
        out = self.runtime_root / "cycles"
        out.mkdir(parents=True, exist_ok=True)
        (out / f"{cycle_id}.json").write_text(json.dumps(record, indent=2, sort_keys=True), encoding="utf-8")

        recommendation_hash = hashlib.sha256(integration_text.encode()).hexdigest()
        for spec in self.children:
            identity = self._identity(spec)
            EvolutionLedger(self._child_root(spec) / "evolution_ledger.jsonl").append(
                identity,
                "competitive_cooperative_cycle_completed",
                {"cycle_id": cycle_id, "objective": objective, "recommendation_sha256": recommendation_hash},
            )
        return record

    def status(self) -> dict[str, Any]:
        nodes = []
        for spec in self.children:
            manifest_path = self._child_root(spec) / "manifest.json"
            nodes.append(json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else asdict(spec))
        return {
            "name": "Gene Recursive Cooperative Evolution",
            "nickname": self.identity.nickname,
            "protocol": "grce/0.2",
            "parent": "gene-node-1",
            "children": nodes,
            "master_ai_objective": self.identity.master_ai_objective,
            "system_plan": list(self.identity.system_plan),
            "constitution_sha256": self.constitution_hash,
        }
