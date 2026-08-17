from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .gden import EvolutionLedger, NodeIdentity
from .identity import GeneIdentity


@dataclass(frozen=True)
class ReplicationPolicy:
    enabled: bool = True
    max_generation: int = 2
    max_total_nodes: int = 7
    children_per_parent: int = 1
    authorized_parents: tuple[str, ...] = ("gene-node-2", "gene-node-3")

    @classmethod
    def load(cls, path: Path) -> "ReplicationPolicy":
        if not path.exists():
            return cls()
        payload = json.loads(path.read_text(encoding="utf-8"))
        return cls(
            enabled=bool(payload.get("enabled", True)),
            max_generation=max(0, int(payload.get("max_generation", 2))),
            max_total_nodes=max(3, int(payload.get("max_total_nodes", 7))),
            children_per_parent=max(0, int(payload.get("children_per_parent", 1))),
            authorized_parents=tuple(str(x) for x in payload.get("authorized_parents", ["gene-node-2", "gene-node-3"])),
        )


@dataclass(frozen=True)
class ReplicaSpec:
    logical_id: str
    parent_id: str
    generation: int
    role: str
    inherited_from: str


class GeneReplicationManager:
    """Bounded, authorized local replication of Gene nodes.

    This is deliberately not an internet self-propagation mechanism. Replicas are
    provisioned only inside the configured runtime root, inherit the same Gene
    identity/plan and Constitution hash, receive a fresh cryptographic node
    identity, and are limited by explicit generation/total-node policy.
    """

    def __init__(self, root: Path, policy: ReplicationPolicy | None = None) -> None:
        self.root = Path(root).resolve()
        self.runtime_root = self.root / "runtime" / "grce"
        self.runtime_root.mkdir(parents=True, exist_ok=True)
        self.identity = GeneIdentity.load(self.root)
        self.constitution_hash = hashlib.sha256((self.root / "GENESIS_CONSTITUTION.md").read_bytes()).hexdigest()
        self.policy = policy or ReplicationPolicy.load(self.root / "config" / "replication.json")
        self.registry_path = self.runtime_root / "replica_registry.json"

    def _load_registry(self) -> dict[str, dict[str, Any]]:
        if not self.registry_path.exists():
            return {}
        payload = json.loads(self.registry_path.read_text(encoding="utf-8"))
        return {str(k): dict(v) for k, v in payload.items()}

    def _save_registry(self, registry: dict[str, dict[str, Any]]) -> None:
        self.registry_path.write_text(json.dumps(registry, indent=2, sort_keys=True), encoding="utf-8")

    @staticmethod
    def _next_id(registry: dict[str, dict[str, Any]]) -> str:
        used = {int(key.rsplit("-", 1)[-1]) for key in registry if key.startswith("gene-node-") and key.rsplit("-", 1)[-1].isdigit()}
        candidate = 4
        while candidate in used:
            candidate += 1
        return f"gene-node-{candidate}"

    def _existing_node_count(self, registry: dict[str, dict[str, Any]]) -> int:
        # Node 1 plus permanent Nodes 2/3 plus replicas.
        return 3 + len(registry)

    def can_replicate(self, parent_id: str, parent_generation: int = 1) -> tuple[bool, str]:
        if not self.policy.enabled:
            return False, "replication_disabled"
        if parent_id not in self.policy.authorized_parents:
            return False, "parent_not_authorized"
        if parent_generation >= self.policy.max_generation:
            return False, "generation_limit"
        registry = self._load_registry()
        if self._existing_node_count(registry) >= self.policy.max_total_nodes:
            return False, "node_limit"
        children = [item for item in registry.values() if item.get("parent_id") == parent_id]
        if len(children) >= self.policy.children_per_parent:
            return False, "parent_child_limit"
        return True, "allowed"

    def replicate(self, parent_id: str, parent_generation: int = 1) -> dict[str, Any]:
        allowed, reason = self.can_replicate(parent_id, parent_generation)
        if not allowed:
            return {"status": "blocked", "reason": reason, "parent_id": parent_id}

        registry = self._load_registry()
        logical_id = self._next_id(registry)
        child_root = self.runtime_root / logical_id
        child_root.mkdir(parents=True, exist_ok=True)
        node_identity = NodeIdentity.load_or_create(child_root / "identity.key")
        generation = parent_generation + 1
        manifest = {
            "logical_id": logical_id,
            "node_id": node_identity.node_id,
            "parent_id": parent_id,
            "generation": generation,
            "role": "replicated_gene_worker",
            "gene_nickname": self.identity.nickname,
            "canonical_name": self.identity.canonical_name,
            "master_ai_objective": self.identity.master_ai_objective,
            "constitution_sha256": self.constitution_hash,
            "core_inheritance": "same_gene_identity_plan_constitution",
            "state_model": "isolated_local_state",
            "replication_scope": "authorized_local_runtime_only",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        (child_root / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
        EvolutionLedger(child_root / "evolution_ledger.jsonl").append(node_identity, "gene_replica_created", manifest)
        registry[logical_id] = manifest
        self._save_registry(registry)
        return {"status": "created", **manifest}

    def seed_first_generation(self) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for parent_id in self.policy.authorized_parents:
            results.append(self.replicate(parent_id, parent_generation=1))
        return results

    def status(self) -> dict[str, Any]:
        registry = self._load_registry()
        return {
            "name": "Gene Bounded Recursive Replication",
            "nickname": self.identity.nickname,
            "policy": asdict(self.policy),
            "total_nodes": self._existing_node_count(registry),
            "replicas": list(registry.values()),
            "scope": "authorized_local_runtime_only",
        }
