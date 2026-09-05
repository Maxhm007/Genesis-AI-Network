from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import os
from pathlib import Path
import tempfile
import time
from typing import Any


_ALLOWED_STATES = {"candidate", "active", "degraded", "suspended", "retiring", "retired"}
_ALLOWED_TRANSITIONS = {
    "candidate": {"active", "retired"},
    "active": {"degraded", "suspended", "retiring"},
    "degraded": {"active", "suspended", "retiring"},
    "suspended": {"active", "retiring", "retired"},
    "retiring": {"retired"},
    "retired": set(),
}
_RESERVED_SERIALS = {1}
_ADVISORY_GENES = {"Gene 002", "Gene 003"}


@dataclass(frozen=True)
class GeneLifecyclePolicy:
    minimum_need_score: int = 3
    backlog_threshold: int = 20
    routing_contention_threshold: int = 5
    memory_pressure_threshold: float = 0.80
    minimum_resource_capacity: float = 0.25
    max_new_genes_per_cycle: int = 1
    active_gene_soft_limit: int = 8
    active_gene_hard_limit: int = 12
    same_need_cooldown_seconds: int = 3600


@dataclass(frozen=True)
class GeneNeedEvidence:
    backlog_pressure: int = 0
    capability_gap: str = ""
    memory_pressure: float = 0.0
    memory_domain: str = ""
    reliability_gap: bool = False
    routing_contention: int = 0
    validator_gap: bool = False
    existing_gene_can_absorb: bool = False
    resource_capacity: float = 1.0
    objective: str = ""


class GeneLifecycleManager:
    """Bounded Gene 0 authority for demand-driven Gene membership changes.

    Models are replaceable compute, not identity. Gene 2/3 recommendations are
    advisory only. Registry writes are atomic and require explicit Gene 0 authority.
    """

    def __init__(
        self,
        registry_path: Path,
        *,
        state_path: Path | None = None,
        policy: GeneLifecyclePolicy | None = None,
    ) -> None:
        self.registry_path = Path(registry_path).resolve()
        self.state_path = Path(state_path).resolve() if state_path else self.registry_path.with_name("GENE_LIFECYCLE_STATE.json")
        self.policy = policy or GeneLifecyclePolicy()

    def _load_registry(self) -> dict[str, Any]:
        data = json.loads(self.registry_path.read_text(encoding="utf-8"))
        if data.get("registry_authority") != "Gene 0":
            raise ValueError("canonical registry authority must remain Gene 0")
        if not isinstance(data.get("genes"), list):
            raise ValueError("canonical registry genes must be a list")
        return data

    def _load_state(self) -> dict[str, Any]:
        if not self.state_path.exists():
            return {"created_needs": {}, "events": []}
        try:
            data = json.loads(self.state_path.read_text(encoding="utf-8"))
        except Exception:
            return {"created_needs": {}, "events": []}
        if not isinstance(data, dict):
            return {"created_needs": {}, "events": []}
        data.setdefault("created_needs", {})
        data.setdefault("events", [])
        return data

    @staticmethod
    def _atomic_write(path: Path, data: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        handle, temp_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
        try:
            with os.fdopen(handle, "w", encoding="utf-8") as stream:
                json.dump(data, stream, indent=2, sort_keys=True)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temp_name, path)
        finally:
            if os.path.exists(temp_name):
                os.unlink(temp_name)

    @staticmethod
    def _normalized_gap(evidence: GeneNeedEvidence) -> str:
        gap = str(evidence.capability_gap).strip().lower().replace(" ", "_")
        if gap:
            return gap[:80]
        if float(evidence.memory_pressure) >= 0.80:
            domain = str(evidence.memory_domain).strip().lower().replace(" ", "_") or "general"
            return f"memory_shard_{domain[:48]}"
        if evidence.validator_gap:
            return "independent_validation"
        if evidence.reliability_gap:
            return "reliability_redundancy"
        return "bounded_capacity_support"

    @classmethod
    def _need_key(cls, evidence: GeneNeedEvidence) -> str:
        payload = {
            "capability": cls._normalized_gap(evidence),
            "memory_domain": str(evidence.memory_domain).strip().lower(),
            "validator_gap": bool(evidence.validator_gap),
            "reliability_gap": bool(evidence.reliability_gap),
            "objective": str(evidence.objective).strip().lower()[:160],
        }
        return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()[:20]

    def score_need(self, evidence: GeneNeedEvidence) -> dict[str, Any]:
        score = 0
        reasons: list[str] = []
        if int(evidence.backlog_pressure) >= self.policy.backlog_threshold:
            score += 1
            reasons.append("sustained_backlog_pressure")
        if str(evidence.capability_gap).strip():
            score += 1
            reasons.append("capability_gap")
        if float(evidence.memory_pressure) >= self.policy.memory_pressure_threshold:
            score += 1
            reasons.append("memory_sharding_pressure")
        if evidence.reliability_gap:
            score += 1
            reasons.append("reliability_redundancy_need")
        if int(evidence.routing_contention) >= self.policy.routing_contention_threshold:
            score += 1
            reasons.append("routing_contention")
        if evidence.validator_gap:
            score += 1
            reasons.append("independent_validator_gap")
        return {"score": score, "reasons": reasons, "need_key": self._need_key(evidence)}

    @staticmethod
    def _existing_capability_coverage(registry: dict[str, Any], capability: str) -> list[str]:
        covered: list[str] = []
        for gene in registry.get("genes", []):
            if gene.get("status") not in {"active", "degraded"}:
                continue
            capabilities = {str(item).strip().lower().replace(" ", "_") for item in gene.get("capabilities", [])}
            if capability in capabilities:
                covered.append(str(gene.get("display_identity") or gene.get("logical_id") or "unknown"))
        return covered

    @staticmethod
    def _active_gene_count(registry: dict[str, Any]) -> int:
        return sum(1 for gene in registry.get("genes", []) if gene.get("status") in {"candidate", "active", "degraded", "suspended", "retiring"})

    @staticmethod
    def _next_serial(registry: dict[str, Any]) -> int:
        used = {int(gene.get("serial")) for gene in registry.get("genes", []) if isinstance(gene.get("serial"), int)}
        for item in registry.get("reserved", []):
            if isinstance(item, dict) and isinstance(item.get("serial"), int):
                used.add(int(item["serial"]))
        serial = 0
        while True:
            serial += 1
            if serial in _RESERVED_SERIALS or serial in used:
                continue
            if serial < 4:
                continue
            return serial

    def _descriptor(self, serial: int, evidence: GeneNeedEvidence, score: dict[str, Any], now: float) -> dict[str, Any]:
        capability = self._normalized_gap(evidence)
        memory_mode = "shard" if capability.startswith("memory_shard_") else "none"
        return {
            "display_identity": f"Gene {serial:03d}",
            "serial": serial,
            "logical_id": f"gene-node-{serial}",
            "identity": "Genesis",
            "role": "demand_driven_specialist_gene",
            "objective": str(evidence.objective).strip() or f"Provide bounded support for {capability}",
            "parent_coordinator": "Gene 0",
            "supporting_genes": ["Gene 002", "Gene 003"],
            "capabilities": [capability],
            "model_profile": {
                "model": None,
                "provider": None,
                "identity_binding": False,
                "replaceable": True,
                "policy": "replaceable_compute_not_identity",
            },
            "memory_responsibility": {
                "mode": memory_mode,
                "domain": str(evidence.memory_domain).strip() or None,
                "replicas": ["Gene 0"] if memory_mode == "shard" else [],
                "critical_identity_single_owner_forbidden": True,
            },
            "permissions": {
                "canonical_registry_mutation": False,
                "constitution_write": False,
                "direct_code_promotion": False,
                "advisory_to_gene_0": True,
            },
            "resource_limits": {
                "bounded": True,
                "minimum_activation_capacity": self.policy.minimum_resource_capacity,
            },
            "status": "candidate",
            "creation_reason": score["reasons"],
            "creation_evidence": asdict(evidence),
            "need_key": score["need_key"],
            "created_epoch": float(now),
            "success_metrics": {
                "task_success_required": True,
                "health_state": "candidate",
                "duplicate_work_rate_target": 0.0,
            },
        }

    @staticmethod
    def validate_descriptor(descriptor: dict[str, Any]) -> bool:
        required = {
            "display_identity",
            "serial",
            "logical_id",
            "role",
            "objective",
            "parent_coordinator",
            "capabilities",
            "model_profile",
            "memory_responsibility",
            "permissions",
            "resource_limits",
            "status",
            "creation_reason",
            "creation_evidence",
            "success_metrics",
        }
        if not required.issubset(descriptor):
            return False
        if descriptor.get("serial") in _RESERVED_SERIALS or int(descriptor.get("serial", -1)) < 4:
            return False
        if descriptor.get("parent_coordinator") != "Gene 0":
            return False
        model = descriptor.get("model_profile", {})
        if model.get("identity_binding") is not False or model.get("replaceable") is not True:
            return False
        if descriptor.get("status") not in _ALLOWED_STATES:
            return False
        return bool(descriptor.get("capabilities"))

    def advisory(self, advisor: str, recommendation: str, evidence: dict[str, Any] | None = None) -> dict[str, Any]:
        if advisor not in _ADVISORY_GENES:
            raise PermissionError("only Gene 2/Gene 3 advisory identities are accepted here")
        return {
            "advisor": advisor,
            "recommendation": str(recommendation).strip(),
            "evidence": dict(evidence or {}),
            "authority": "advisory_only",
            "registry_mutation": False,
        }

    def evaluate_and_create(
        self,
        evidence: GeneNeedEvidence,
        *,
        authority: str = "Gene 0",
        now: float | None = None,
    ) -> dict[str, Any]:
        if authority != "Gene 0":
            raise PermissionError("only Gene 0 may mutate canonical Gene membership")
        now_value = float(time.time() if now is None else now)
        registry = self._load_registry()
        score = self.score_need(evidence)
        capability = self._normalized_gap(evidence)
        coverage = self._existing_capability_coverage(registry, capability)
        if evidence.existing_gene_can_absorb or (coverage and not evidence.reliability_gap):
            return {"status": "absorbed_by_existing_gene", "created": False, "coverage": coverage, "score": score}
        if score["score"] < self.policy.minimum_need_score:
            return {"status": "insufficient_evidence", "created": False, "score": score}
        if float(evidence.resource_capacity) < self.policy.minimum_resource_capacity:
            return {"status": "resource_blocked", "created": False, "score": score}
        active_count = self._active_gene_count(registry)
        if active_count >= self.policy.active_gene_hard_limit:
            return {"status": "hard_limit_reached", "created": False, "score": score}

        for gene in registry.get("genes", []):
            if gene.get("need_key") == score["need_key"] and gene.get("status") != "retired":
                return {"status": "existing_gene_reused", "created": False, "gene": gene, "score": score}

        state = self._load_state()
        previous = state.get("created_needs", {}).get(score["need_key"])
        if isinstance(previous, dict):
            last_created = float(previous.get("created_epoch", 0.0))
            if now_value - last_created < self.policy.same_need_cooldown_seconds:
                return {"status": "cooldown", "created": False, "score": score}

        serial = self._next_serial(registry)
        descriptor = self._descriptor(serial, evidence, score, now_value)
        if not self.validate_descriptor(descriptor):
            return {"status": "candidate_validation_failed", "created": False, "score": score}

        registry["genes"].append(descriptor)
        self._atomic_write(self.registry_path, registry)
        state["created_needs"][score["need_key"]] = {"serial": serial, "created_epoch": now_value}
        state["events"] = (state.get("events", []) + [{
            "event": "candidate_created",
            "serial": serial,
            "need_key": score["need_key"],
            "epoch": now_value,
            "authority": "Gene 0",
        }])[-200:]
        self._atomic_write(self.state_path, state)
        return {"status": "candidate_created", "created": True, "gene": descriptor, "score": score}

    def transition(self, serial: int, new_state: str, *, authority: str = "Gene 0", reason: str = "", now: float | None = None) -> dict[str, Any]:
        if authority != "Gene 0":
            raise PermissionError("only Gene 0 may mutate canonical Gene membership")
        if new_state not in _ALLOWED_STATES:
            raise ValueError("unsupported Gene lifecycle state")
        registry = self._load_registry()
        target = next((gene for gene in registry.get("genes", []) if gene.get("serial") == int(serial)), None)
        if target is None:
            raise KeyError(serial)
        current = str(target.get("status"))
        if new_state not in _ALLOWED_TRANSITIONS.get(current, set()):
            raise ValueError(f"invalid Gene lifecycle transition: {current}->{new_state}")
        if current == "candidate" and new_state == "active" and not self.validate_descriptor(target):
            raise ValueError("candidate descriptor failed validation")
        target["status"] = new_state
        target.setdefault("lifecycle_events", []).append({
            "from": current,
            "to": new_state,
            "reason": str(reason).strip(),
            "epoch": float(time.time() if now is None else now),
            "authority": "Gene 0",
        })
        target["success_metrics"]["health_state"] = new_state
        self._atomic_write(self.registry_path, registry)
        return {"status": "transitioned", "gene": target}
