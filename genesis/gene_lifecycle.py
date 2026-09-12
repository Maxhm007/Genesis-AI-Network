from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import tempfile
from typing import Iterable


LIFECYCLE_STATES = {"candidate", "active", "degraded", "suspended", "retiring", "retired"}
RESERVED_SERIALS = {1}


@dataclass(frozen=True)
class GeneLifecycleConfig:
    evidence_threshold: int = 2
    max_new_genes_per_cycle: int = 1
    soft_active_limit: int = 8
    hard_active_limit: int = 16
    cooldown_seconds: int = 3600


@dataclass(frozen=True)
class GeneNeed:
    role: str
    objective: str
    capabilities: tuple[str, ...]
    evidence: dict[str, int | bool | str]
    memory_responsibility: str = ""
    replicas: tuple[str, ...] = ()
    provider_policy: str = "replaceable_compute_not_identity"
    permissions: tuple[str, ...] = ("task_execute", "knowledge_read", "knowledge_write_candidate")
    resource_limits: dict[str, int | float | str] = field(default_factory=lambda: {"max_parallel_tasks": 1})
    success_metrics: tuple[str, ...] = ("task_success_rate", "health_status")


class GeneLifecycleManager:
    """Bounded, deterministic Gene 0 lifecycle authority.

    This manages real Gene registry entries. It is intentionally separate from
    dynamic AI-team roles in ``genesis.team``.
    """

    def __init__(self, registry_path: Path, config: GeneLifecycleConfig | None = None) -> None:
        self.registry_path = Path(registry_path)
        self.config = config or GeneLifecycleConfig()

    def _load(self) -> dict:
        data = json.loads(self.registry_path.read_text(encoding="utf-8"))
        if data.get("registry_authority") != "Gene 0":
            raise RuntimeError("Gene 0 is not the canonical registry authority")
        if not isinstance(data.get("genes"), list):
            raise RuntimeError("invalid Gene registry: genes must be a list")
        return data

    def _atomic_write(self, data: dict) -> None:
        self.registry_path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(data, indent=2, sort_keys=False) + "\n"
        fd, temp_name = tempfile.mkstemp(prefix="gene-registry-", suffix=".json", dir=str(self.registry_path.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_name, self.registry_path)
        finally:
            if os.path.exists(temp_name):
                os.unlink(temp_name)

    @staticmethod
    def _normalized_capabilities(values: Iterable[str]) -> set[str]:
        return {str(value).strip().lower() for value in values if str(value).strip()}

    def need_score(self, need: GeneNeed) -> int:
        positive_keys = (
            "backlog_pressure",
            "capability_gap",
            "memory_pressure",
            "reliability_need",
            "routing_contention",
            "independent_validation_need",
        )
        score = 0
        for key in positive_keys:
            value = need.evidence.get(key, 0)
            if isinstance(value, bool):
                score += int(value)
            elif isinstance(value, (int, float)) and value > 0:
                score += 1
        return score

    def _active_genes(self, registry: dict) -> list[dict]:
        return [gene for gene in registry["genes"] if gene.get("status") in {"candidate", "active", "degraded", "suspended", "retiring"}]

    def existing_gene_can_absorb(self, registry: dict, need: GeneNeed) -> bool:
        required = self._normalized_capabilities(need.capabilities)
        if not required:
            return True
        for gene in registry["genes"]:
            if gene.get("status") not in {"active", "degraded"}:
                continue
            current = self._normalized_capabilities(gene.get("capabilities") or [])
            profile = gene.get("model_profile") or {}
            current |= self._normalized_capabilities(profile.get("specialization") or [])
            if required <= current:
                return True
        return False

    def next_serial(self, registry: dict) -> int:
        used = {int(gene.get("serial")) for gene in registry["genes"] if str(gene.get("serial", "")).isdigit()}
        for row in registry.get("reserved") or []:
            serial = row.get("serial")
            if isinstance(serial, int):
                used.add(serial)
        used |= RESERVED_SERIALS
        serial = 0
        while serial in used:
            serial += 1
        return serial

    @staticmethod
    def _need_key(need: GeneNeed) -> str:
        caps = ",".join(sorted(GeneLifecycleManager._normalized_capabilities(need.capabilities)))
        return f"{need.role.strip().lower()}::{caps}::{need.memory_responsibility.strip().lower()}"

    def evaluate(self, need: GeneNeed) -> dict:
        registry = self._load()
        score = self.need_score(need)
        if score < self.config.evidence_threshold:
            return {"action": "none", "reason": "insufficient_evidence", "score": score}
        if self.existing_gene_can_absorb(registry, need):
            return {"action": "none", "reason": "existing_gene_can_absorb", "score": score}
        if len(self._active_genes(registry)) >= self.config.hard_active_limit:
            return {"action": "none", "reason": "hard_active_gene_limit", "score": score}

        need_key = self._need_key(need)
        for gene in registry["genes"]:
            if gene.get("creation_need_key") == need_key and gene.get("status") != "retired":
                return {"action": "none", "reason": "duplicate_need", "gene": gene, "score": score}

        serial = self.next_serial(registry)
        if serial in RESERVED_SERIALS:
            raise AssertionError("reserved Gene serial selected")
        return {"action": "create", "serial": serial, "score": score, "need_key": need_key}

    def create_candidate(self, need: GeneNeed) -> dict:
        decision = self.evaluate(need)
        if decision.get("action") != "create":
            return decision

        registry = self._load()
        serial = int(decision["serial"])
        now = datetime.now(timezone.utc).isoformat()
        descriptor = {
            "display_identity": f"Gene {serial:03d}",
            "serial": serial,
            "logical_id": f"gene-node-{serial}",
            "role": need.role,
            "objective": need.objective,
            "parent_coordinator": "Gene 0",
            "supporting_genes": ["Gene 002", "Gene 003"],
            "status": "candidate",
            "identity": "Genesis",
            "capabilities": list(need.capabilities),
            "model_policy": need.provider_policy,
            "memory_responsibility": need.memory_responsibility,
            "memory_replicas": list(need.replicas),
            "permissions": list(need.permissions),
            "resource_limits": dict(need.resource_limits),
            "creation_reason_evidence": dict(need.evidence),
            "creation_need_key": decision["need_key"],
            "success_metrics": list(need.success_metrics),
            "created_at": now,
            "lifecycle_history": [{"state": "candidate", "at": now, "reason": "Gene 0 demand evaluation"}],
        }
        registry["genes"].append(descriptor)
        self._atomic_write(registry)
        return {"action": "created_candidate", "gene": descriptor}

    def transition(self, serial: int, new_state: str, reason: str) -> dict:
        if new_state not in LIFECYCLE_STATES:
            raise ValueError(f"invalid lifecycle state: {new_state}")
        if serial in {0, 1, 2, 3} and new_state == "retired":
            raise ValueError("core/reserved Genes cannot be retired by autonomous lifecycle manager")
        registry = self._load()
        gene = next((row for row in registry["genes"] if row.get("serial") == serial), None)
        if gene is None:
            raise KeyError(f"unknown Gene serial: {serial}")
        allowed = {
            "candidate": {"active", "suspended", "retired"},
            "active": {"degraded", "suspended", "retiring"},
            "degraded": {"active", "suspended", "retiring"},
            "suspended": {"active", "retiring", "retired"},
            "retiring": {"retired"},
            "retired": set(),
        }
        current = str(gene.get("status") or "")
        if new_state == current:
            return {"action": "unchanged", "gene": gene}
        if new_state not in allowed.get(current, set()):
            raise ValueError(f"invalid lifecycle transition: {current} -> {new_state}")
        now = datetime.now(timezone.utc).isoformat()
        gene["status"] = new_state
        gene.setdefault("lifecycle_history", []).append({"state": new_state, "at": now, "reason": reason})
        self._atomic_write(registry)
        return {"action": "transitioned", "gene": gene}

    def activate_if_valid(self, serial: int) -> dict:
        registry = self._load()
        gene = next((row for row in registry["genes"] if row.get("serial") == serial), None)
        if gene is None:
            raise KeyError(f"unknown Gene serial: {serial}")
        required = ("display_identity", "logical_id", "role", "objective", "capabilities", "model_policy", "resource_limits", "success_metrics")
        if any(not gene.get(field) for field in required):
            return {"action": "none", "reason": "descriptor_validation_failed", "gene": gene}
        if serial in RESERVED_SERIALS:
            return {"action": "none", "reason": "reserved_serial", "gene": gene}
        return self.transition(serial, "active", "descriptor/configuration validated")
