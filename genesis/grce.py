from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .gden import ContributionPolicy, EvolutionLedger, NodeIdentity, make_advertisement
from .providers import ProviderRegistry
from .team import AITeam


@dataclass(frozen=True)
class ChildGeneSpec:
    logical_id: str
    role: str
    specialties: tuple[str, ...]
    max_cpu_percent: int = 20
    max_memory_mb: int = 2048
    max_storage_mb: int = 4096


DEFAULT_CHILDREN = (
    ChildGeneSpec(
        logical_id="gene-node-2",
        role="explorer_researcher",
        specialties=("research", "model_discovery", "architecture", "experimentation"),
    ),
    ChildGeneSpec(
        logical_id="gene-node-3",
        role="engineer_challenger",
        specialties=("engineering", "repair", "review", "validation_challenge"),
    ),
)


class GeneFederation:
    """Authorized cooperative Gene federation for Nodes 1, 2 and 3.

    Child nodes inherit the same Constitution hash but keep independent local
    identities, state directories, ledgers and work products. They may propose,
    challenge and synthesize improvements; they cannot promote source changes or
    create additional child nodes without an explicit authorized node spec.
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
        self.runtime_root = self.root / "runtime" / "grce"
        self.runtime_root.mkdir(parents=True, exist_ok=True)
        self.constitution_hash = hashlib.sha256((self.root / "GENESIS_CONSTITUTION.md").read_bytes()).hexdigest()

    def _child_root(self, spec: ChildGeneSpec) -> Path:
        return self.runtime_root / spec.logical_id

    def _identity(self, spec: ChildGeneSpec) -> NodeIdentity:
        return NodeIdentity.load_or_create(self._child_root(spec) / "identity.key")

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

    def cooperative_cycle(self, objective: str) -> dict[str, Any]:
        manifests = {item["logical_id"]: item for item in self.provision()}
        node2 = next(spec for spec in self.children if spec.logical_id == "gene-node-2")
        node3 = next(spec for spec in self.children if spec.logical_id == "gene-node-3")

        explorer_team = AITeam(self.providers)
        challenger_team = AITeam(self.providers)
        integrator_team = AITeam(self.providers)

        explorer_outputs = explorer_team.run_task(
            "Act as Gene Node 2, the independent explorer/researcher. "
            "Find the strongest evidence-backed approach to this objective, alternative approaches, dependencies, risks, "
            "and the smallest testable next improvement. Do not claim unmeasured capability.\nObjective: " + objective,
            context=f"constitution={self.constitution_hash}; role={node2.role}; specialties={','.join(node2.specialties)}",
        )
        explorer_text = self._render(explorer_outputs)

        challenger_outputs = challenger_team.run_task(
            "Act as Gene Node 3, the independent engineer/challenger. Critique Node 2's proposal, identify failure modes, "
            "security or validation weaknesses, and propose an independently testable implementation or better alternative. "
            "Do not approve by agreement alone.\nObjective: " + objective + "\nNode 2 evidence:\n" + explorer_text,
            context=f"constitution={self.constitution_hash}; role={node3.role}; specialties={','.join(node3.specialties)}",
        )
        challenger_text = self._render(challenger_outputs)

        integration_outputs = integrator_team.run_task(
            "Act as Gene Node 1, coordinator/integrator. Synthesize Nodes 2 and 3 into one bounded development recommendation. "
            "Prefer independently testable changes, retain disagreements, and require normal candidate tests plus independent "
            "validator quorum before promotion. Do not merge or activate code directly.\nObjective: "
            + objective
            + "\nNode 2:\n"
            + explorer_text
            + "\nNode 3:\n"
            + challenger_text,
            context="role=coordinator_integrator; promotion=independent_validator_quorum_required",
        )
        integration_text = self._render(integration_outputs)

        cycle_id = hashlib.sha256(
            f"{datetime.now(timezone.utc).isoformat()}|{objective}|{explorer_text}|{challenger_text}".encode("utf-8")
        ).hexdigest()[:20]
        record = {
            "cycle_id": cycle_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "objective": objective,
            "nodes": manifests,
            "node_2": {"role": node2.role, "outputs": explorer_outputs},
            "node_3": {"role": node3.role, "outputs": challenger_outputs},
            "node_1": {"role": "coordinator_integrator", "outputs": integration_outputs},
            "recommendation": integration_text,
            "promotion_rule": "candidate_only_until_tests_and_independent_validator_quorum",
            "replication_rule": "additional_nodes_require_explicit_authorized_spec",
        }
        out = self.runtime_root / "cycles"
        out.mkdir(parents=True, exist_ok=True)
        (out / f"{cycle_id}.json").write_text(json.dumps(record, indent=2, sort_keys=True), encoding="utf-8")

        for spec in self.children:
            identity = self._identity(spec)
            EvolutionLedger(self._child_root(spec) / "evolution_ledger.jsonl").append(
                identity,
                "cooperative_cycle_completed",
                {"cycle_id": cycle_id, "objective": objective, "recommendation_sha256": hashlib.sha256(integration_text.encode()).hexdigest()},
            )
        return record

    def status(self) -> dict[str, Any]:
        nodes = []
        for spec in self.children:
            manifest_path = self._child_root(spec) / "manifest.json"
            nodes.append(json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else asdict(spec))
        return {
            "name": "Gene Recursive Cooperative Evolution",
            "protocol": "grce/0.1",
            "parent": "gene-node-1",
            "children": nodes,
            "constitution_sha256": self.constitution_hash,
        }
