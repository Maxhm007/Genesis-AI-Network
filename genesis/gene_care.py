from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .gden import EvolutionLedger, NodeIdentity
from .gene_names import canonical_gene_name
from .peer_network import GenePeerNetwork


@dataclass(frozen=True)
class GeneHealth:
    logical_id: str
    status: str
    queue_depth: int = 0
    blocked_tasks: int = 0
    error_count: int = 0
    oldest_task_age_seconds: int = 0
    note: str = ""

    def needs_care(self) -> bool:
        return (
            self.status in {"degraded", "failed", "overloaded", "isolated"}
            or self.blocked_tasks > 0
            or self.error_count > 0
        )


class GeneCareNetwork:
    """Mutual care, assistance and bounded repair between independent Gene peers.

    Care never makes one Gene subordinate to another. A helper may diagnose,
    share evidence, offer capacity, propose a repair and verify recovery, but
    structural code changes still use the normal candidate/test/validator path.
    """

    def __init__(self, root: Path) -> None:
        self.root = Path(root).resolve()
        self.runtime_root = self.root / "runtime" / "grce"
        self.runtime_root.mkdir(parents=True, exist_ok=True)
        self.peers = GenePeerNetwork(self.root)

    def _node_root(self, logical_id: str) -> Path:
        path = self.runtime_root / logical_id
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _identity(self, logical_id: str) -> NodeIdentity:
        return NodeIdentity.load_or_create(self._node_root(logical_id) / "identity.key")

    def publish_health(self, health: GeneHealth) -> dict[str, Any]:
        identity = self._identity(health.logical_id)
        payload = {
            **asdict(health),
            "gene_name": canonical_gene_name(health.logical_id),
            "node_id": identity.node_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        payload["signature"] = identity.sign(dict(payload))
        path = self._node_root(health.logical_id) / "health.json"
        path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        return payload

    def request_help(self, requester_id: str, helper_id: str, problem: str) -> dict[str, Any]:
        return self.peers.send_message(
            requester_id,
            helper_id,
            subject="Gene care request",
            body=problem,
            message_type="care_request",
        )

    def offer_help(self, helper_id: str, target_id: str, diagnosis: str, proposed_action: str) -> dict[str, Any]:
        message = self.peers.send_message(
            helper_id,
            target_id,
            subject="Gene care offer",
            body=json.dumps({"diagnosis": diagnosis, "proposed_action": proposed_action}, sort_keys=True),
            message_type="care_offer",
        )
        self._record_care_event(
            helper_id,
            "care_offered",
            {"target_id": target_id, "diagnosis": diagnosis, "proposed_action": proposed_action},
        )
        return message

    def record_repair_proposal(
        self,
        helper_id: str,
        target_id: str,
        problem: str,
        repair: str,
        evidence: dict[str, Any],
    ) -> dict[str, Any]:
        packet = self.peers.publish_knowledge(
            helper_id,
            topic="gene-care",
            claim=f"Repair proposal for {canonical_gene_name(target_id)}: {repair}",
            evidence={"problem": problem, **dict(evidence)},
            provenance={
                "helper_id": helper_id,
                "helper_name": canonical_gene_name(helper_id),
                "target_id": target_id,
                "target_name": canonical_gene_name(target_id),
                "promotion_rule": "candidate_only_until_tests_and_independent_validator_quorum",
            },
        )
        self._record_care_event(helper_id, "repair_proposed", {"target_id": target_id, "packet_id": packet["packet_id"]})
        return packet

    def verify_recovery(self, helper_id: str, target_health: GeneHealth, evidence: dict[str, Any]) -> dict[str, Any]:
        recovered = not target_health.needs_care() and target_health.status == "healthy"
        payload = {
            "helper_id": helper_id,
            "helper_name": canonical_gene_name(helper_id),
            "target_id": target_health.logical_id,
            "target_name": canonical_gene_name(target_health.logical_id),
            "recovered": recovered,
            "health": asdict(target_health),
            "evidence": dict(evidence),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        self._record_care_event(helper_id, "recovery_verified" if recovered else "care_continues", payload)
        return payload

    def _record_care_event(self, logical_id: str, event_type: str, payload: dict[str, Any]) -> None:
        identity = self._identity(logical_id)
        ledger = EvolutionLedger(self._node_root(logical_id) / "evolution_ledger.jsonl")
        ledger.append(identity, event_type, payload)
        journal = self._node_root(logical_id) / "care.jsonl"
        with journal.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({"event_type": event_type, **payload}, sort_keys=True) + "\n")

    def care_for(self, helper_id: str, target_health: GeneHealth, diagnosis: str, proposed_action: str) -> dict[str, Any]:
        if not target_health.needs_care():
            return {
                "status": "no_care_needed",
                "helper": canonical_gene_name(helper_id),
                "target": canonical_gene_name(target_health.logical_id),
            }
        offer = self.offer_help(helper_id, target_health.logical_id, diagnosis, proposed_action)
        return {
            "status": "care_offered",
            "helper": canonical_gene_name(helper_id),
            "target": canonical_gene_name(target_health.logical_id),
            "message_id": offer["message_id"],
            "next": "target independently evaluates help; repair evidence must pass normal validation before structural promotion",
        }
