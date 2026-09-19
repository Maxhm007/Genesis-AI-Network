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
    max_total_parallel_tasks: int = 8


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

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)

    @staticmethod
    def _parse_time(value: object) -> datetime | None:
        text = str(value or "").strip()
        if not text:
            return None
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)

    def _record_decision(self, registry: dict, action: str, reason: str, **details: object) -> None:
        row = {
            "at": self._now().isoformat(),
            "authority": "Gene 0",
            "action": action,
            "reason": reason,
        }
        row.update({key: value for key, value in details.items() if value is not None})
        registry.setdefault("lifecycle_decisions", []).append(row)
        registry["lifecycle_decisions"] = registry["lifecycle_decisions"][-500:]

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

    def _cooldown_remaining(self, registry: dict, need_key: str) -> int:
        if self.config.cooldown_seconds <= 0:
            return 0
        now = self._now()
        latest: datetime | None = None
        for gene in registry["genes"]:
            if gene.get("creation_need_key") != need_key:
                continue
            stamp = self._parse_time(gene.get("created_at"))
            history = gene.get("lifecycle_history") or []
            for row in history:
                if isinstance(row, dict):
                    stamp = max(
                        [value for value in (stamp, self._parse_time(row.get("at"))) if value is not None],
                        default=stamp,
                    )
            if stamp is not None and (latest is None or stamp > latest):
                latest = stamp
        if latest is None:
            return 0
        elapsed = max(0.0, (now - latest).total_seconds())
        return max(0, int(self.config.cooldown_seconds - elapsed))

    def evaluate(self, need: GeneNeed) -> dict:
        registry = self._load()
        score = self.need_score(need)
        active_count = len(self._active_genes(registry))
        need_key = self._need_key(need)

        def none(reason: str, **extra: object) -> dict:
            result = {"action": "none", "reason": reason, "score": score, **extra}
            self._record_decision(registry, "no_create", reason, need_key=need_key, score=score, **extra)
            self._atomic_write(registry)
            return result

        if score < self.config.evidence_threshold:
            return none("insufficient_evidence")
        if self.existing_gene_can_absorb(registry, need):
            return none("existing_gene_can_absorb")
        if active_count >= self.config.hard_active_limit:
            return none("hard_active_gene_limit", active_count=active_count)
        if active_count >= self.config.soft_active_limit:
            return none("soft_active_gene_limit", active_count=active_count)

        for gene in registry["genes"]:
            if gene.get("creation_need_key") == need_key and gene.get("status") != "retired":
                return none("duplicate_need", gene=gene)

        cooldown_remaining = self._cooldown_remaining(registry, need_key)
        if cooldown_remaining > 0:
            return none("cooldown_active", cooldown_remaining=cooldown_remaining)

        serial = self.next_serial(registry)
        if serial in RESERVED_SERIALS:
            raise AssertionError("reserved Gene serial selected")
        self._record_decision(registry, "create_candidate_planned", "demand_threshold_met", need_key=need_key, score=score, serial=serial)
        self._atomic_write(registry)
        return {"action": "create", "serial": serial, "score": score, "need_key": need_key}

    def create_candidate(self, need: GeneNeed) -> dict:
        decision = self.evaluate(need)
        if decision.get("action") != "create":
            return decision

        registry = self._load()
        serial = int(decision["serial"])
        now = self._now().isoformat()
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
        self._record_decision(
            registry,
            "created_candidate",
            "Gene 0 demand evaluation",
            serial=serial,
            need_key=decision["need_key"],
            score=decision["score"],
        )
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
        now = self._now().isoformat()
        gene["status"] = new_state
        gene.setdefault("lifecycle_history", []).append({"state": new_state, "at": now, "reason": reason})
        self._record_decision(registry, "transition", reason, serial=serial, from_state=current, to_state=new_state)
        self._atomic_write(registry)
        return {"action": "transitioned", "gene": gene}

    def _parallel_task_budget_used(self, registry: dict, *, exclude_serial: int | None = None) -> int:
        total = 0
        for gene in registry["genes"]:
            if gene.get("serial") == exclude_serial:
                continue
            if gene.get("status") not in {"active", "degraded"}:
                continue
            limits = gene.get("resource_limits") or {}
            try:
                total += max(0, int(limits.get("max_parallel_tasks", 0)))
            except (TypeError, ValueError):
                continue
        return total

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
        if len([row for row in registry["genes"] if row.get("status") in {"active", "degraded"}]) >= self.config.hard_active_limit:
            return {"action": "none", "reason": "hard_active_gene_limit", "gene": gene}

        limits = gene.get("resource_limits") or {}
        try:
            requested_parallel = max(0, int(limits.get("max_parallel_tasks", 0)))
        except (TypeError, ValueError):
            return {"action": "none", "reason": "invalid_resource_limits", "gene": gene}
        budget_used = self._parallel_task_budget_used(registry, exclude_serial=serial)
        if budget_used + requested_parallel > self.config.max_total_parallel_tasks:
            return {
                "action": "none",
                "reason": "resource_budget_exceeded",
                "gene": gene,
                "budget_used": budget_used,
                "requested_parallel_tasks": requested_parallel,
            }
        if gene.get("memory_responsibility") and any(
            token in str(gene.get("memory_responsibility") or "").lower()
            for token in ("identity", "governance", "constitution", "genesis block")
        ):
            replicas = {str(value) for value in gene.get("memory_replicas") or []}
            if not replicas & {"Gene 0", "Gene 002", "Gene 003"}:
                return {"action": "none", "reason": "critical_memory_requires_core_replica", "gene": gene}
        return self.transition(serial, "active", "descriptor/configuration and resource budget validated")

    def evaluate_cycle(self, needs: Iterable[GeneNeed]) -> list[dict]:
        results: list[dict] = []
        created = 0
        for need in needs:
            if created >= self.config.max_new_genes_per_cycle:
                results.append({
                    "action": "none",
                    "reason": "cycle_spawn_limit",
                    "need_key": self._need_key(need),
                })
                continue
            result = self.create_candidate(need)
            results.append(result)
            if result.get("action") == "created_candidate":
                created += 1
        return results

    def merge_responsibilities(self, source_serial: int, target_serial: int, reason: str) -> dict:
        if source_serial == target_serial:
            raise ValueError("source and target Gene must differ")
        registry = self._load()
        source = next((row for row in registry["genes"] if row.get("serial") == source_serial), None)
        target = next((row for row in registry["genes"] if row.get("serial") == target_serial), None)
        if source is None or target is None:
            raise KeyError("unknown source or target Gene")
        if source_serial in {0, 1, 2, 3}:
            raise ValueError("core/reserved Gene responsibilities cannot be autonomously merged away")
        if target.get("status") not in {"active", "degraded"}:
            raise ValueError("target Gene must be active or degraded")

        target_caps = list(dict.fromkeys([*(target.get("capabilities") or []), *(source.get("capabilities") or [])]))
        target["capabilities"] = target_caps
        source_memory = str(source.get("memory_responsibility") or "").strip()
        if source_memory:
            responsibilities = list(target.get("memory_responsibilities") or [])
            primary = str(target.get("memory_responsibility") or "").strip()
            if primary:
                responsibilities.append(primary)
            responsibilities.append(source_memory)
            target["memory_responsibilities"] = list(dict.fromkeys(value for value in responsibilities if value))
        replicas = list(dict.fromkeys([*(target.get("memory_replicas") or []), *(source.get("memory_replicas") or [])]))
        target["memory_replicas"] = replicas

        now = self._now().isoformat()
        source["status"] = "retiring"
        source.setdefault("lifecycle_history", []).append({
            "state": "retiring",
            "at": now,
            "reason": reason,
            "responsibilities_transferred_to": target_serial,
        })
        target.setdefault("lifecycle_history", []).append({
            "state": target.get("status"),
            "at": now,
            "reason": reason,
            "responsibilities_received_from": source_serial,
        })
        self._record_decision(
            registry,
            "merge_responsibilities",
            reason,
            source_serial=source_serial,
            target_serial=target_serial,
        )
        self._atomic_write(registry)
        return {"action": "responsibilities_merged", "source": source, "target": target}

    def route_memory_query(self, responsibility: str) -> list[dict]:
        registry = self._load()
        query = str(responsibility or "").strip().lower()
        if not query:
            return []
        matches: list[dict] = []
        for gene in registry["genes"]:
            if gene.get("status") not in {"active", "degraded"}:
                continue
            responsibilities = {
                str(gene.get("memory_responsibility") or "").strip().lower(),
                *{
                    str(value).strip().lower()
                    for value in gene.get("memory_responsibilities") or []
                },
            }
            responsibilities.discard("")
            if any(query in value or value in query for value in responsibilities):
                matches.append(gene)
        if matches:
            return matches
        coordinator = next(
            (gene for gene in registry["genes"] if gene.get("serial") == 0 and gene.get("status") == "active"),
            None,
        )
        return [coordinator] if coordinator is not None else []
