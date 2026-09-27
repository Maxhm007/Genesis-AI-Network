from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

from genesis.peer_compute import PeerComputeModule, PeerWorkLease
from genesis.peer_network import GenePeerNetwork


RESEARCH_CAPABILITIES = {"research", "validation", "review"}
ENGINEERING_CAPABILITIES = {"engineering", "coding", "repair", "challenge"}
GENE_BY_CAPABILITY = {
    "research": "gene-node-2",
    "validation": "gene-node-2",
    "review": "gene-node-2",
    "engineering": "gene-node-3",
    "coding": "gene-node-3",
    "repair": "gene-node-3",
    "challenge": "gene-node-3",
}


@dataclass(frozen=True)
class DelegatedWork:
    task_id: str
    parent_issue: int
    authoritative_repo: str
    target: str
    capability: str
    peer_logical_id: str
    lease: dict[str, Any]
    created_at: str
    expires_at: str
    status: str = "leased"
    challenge_mode: bool = False

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


class BacklogDelegationRouter:
    """Gene 0 authority for bounded work delegation to idle supporting Genes.

    Delegation never transfers GitHub Issue ownership or closure authority.
    Supporting Genes may only return signed evidence/candidates for Gene 0 to
    validate and ingest through the existing validation/promotion path.
    """

    def __init__(
        self,
        root: Path,
        *,
        authoritative_repo: str = "Maxhm007/Genesis-AI-Network",
        backlog_threshold: int = 3,
        lease_seconds: int = 900,
    ) -> None:
        self.root = Path(root)
        self.authoritative_repo = authoritative_repo
        self.backlog_threshold = max(1, int(backlog_threshold))
        self.lease_seconds = max(60, min(int(lease_seconds), 3600))
        self.peer_compute = PeerComputeModule()
        self.peer_network = GenePeerNetwork(self.root)
        self.state_path = self.root / "runtime" / "delegation" / "leases.json"
        self.audit_path = self.root / "runtime" / "delegation" / "audit.jsonl"

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)

    @staticmethod
    def classify(issue: dict[str, Any]) -> str:
        text = (
            str(issue.get("title") or "") + "\n" + str(issue.get("body") or "")
        ).lower()
        ordered = (
            ("validation", ("validate", "validation", "verify", "review")),
            ("research", ("research", "investigate", "evidence", "compare")),
            ("challenge", ("challenge", "adversarial", "critique")),
            ("repair", ("repair", "fix", "failure", "bug")),
            ("coding", ("code", "coding", "implement", "python", "workflow")),
            ("engineering", ("engineering", "architecture", "integration")),
        )
        for capability, needles in ordered:
            if any(needle in text for needle in needles):
                return capability
        return ""

    @staticmethod
    def peer_for(capability: str) -> str:
        return GENE_BY_CAPABILITY.get(str(capability or "").strip().lower(), "")

    def _load(self) -> list[dict[str, Any]]:
        if not self.state_path.exists():
            return []
        try:
            data = json.loads(self.state_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return []
        return [row for row in data if isinstance(row, dict)] if isinstance(data, list) else []

    def _save(self, rows: Iterable[dict[str, Any]]) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(
            json.dumps(list(rows), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    def _audit(self, event: str, **details: Any) -> None:
        self.audit_path.parent.mkdir(parents=True, exist_ok=True)
        row = {"at": self._now().isoformat(), "event": event, **details}
        with self.audit_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, sort_keys=True) + "\n")

    def active(self, *, now: datetime | None = None) -> list[dict[str, Any]]:
        now = now or self._now()
        rows = []
        for row in self._load():
            if row.get("status") != "leased":
                continue
            try:
                expires = datetime.fromisoformat(str(row.get("expires_at") or "").replace("Z", "+00:00"))
            except ValueError:
                continue
            if expires.tzinfo is None:
                expires = expires.replace(tzinfo=timezone.utc)
            if expires > now:
                rows.append(row)
        return rows

    def supporting_gene_idle(self, peer_open_counts: dict[str, int], peer_logical_id: str) -> bool:
        return int(peer_open_counts.get(peer_logical_id, 0) or 0) == 0 and not any(
            row.get("peer_logical_id") == peer_logical_id for row in self.active()
        )

    def should_delegate(
        self,
        *,
        gene0_open_count: int,
        peer_open_counts: dict[str, int],
        capability: str,
    ) -> tuple[bool, str]:
        if int(gene0_open_count) < self.backlog_threshold:
            return False, "backlog_below_threshold"
        peer = self.peer_for(capability)
        if not peer:
            return False, "unsupported_capability"
        if not self.supporting_gene_idle(peer_open_counts, peer):
            return False, "supporting_gene_busy"
        return True, "eligible"

    def _target_conflict(self, target: str, peer: str, *, challenge_mode: bool) -> bool:
        if not target:
            return False
        for row in self.active():
            if row.get("target") != target:
                continue
            if row.get("peer_logical_id") == peer:
                return True
            if challenge_mode and bool(row.get("challenge_mode")):
                continue
            return True
        return False

    def delegate(
        self,
        issue: dict[str, Any],
        *,
        gene0_open_count: int,
        peer_open_counts: dict[str, int],
        target: str,
        capability: str | None = None,
        challenge_mode: bool = False,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        now = now or self._now()
        parent_issue = int(issue.get("number") or 0)
        if parent_issue <= 0:
            return {"status": "rejected", "reason": "invalid_parent_issue"}
        capability = (capability or self.classify(issue)).strip().lower()
        allowed, reason = self.should_delegate(
            gene0_open_count=gene0_open_count,
            peer_open_counts=peer_open_counts,
            capability=capability,
        )
        if not allowed:
            self._audit("delegation_rejected", parent_issue=parent_issue, reason=reason, capability=capability)
            return {"status": "rejected", "reason": reason}
        peer = self.peer_for(capability)
        if self._target_conflict(target, peer, challenge_mode=challenge_mode):
            self._audit("delegation_rejected", parent_issue=parent_issue, reason="target_conflict", target=target)
            return {"status": "rejected", "reason": "target_conflict"}

        task_id = f"gene0-issue-{parent_issue}-{capability}"
        payload = {
            "parent_issue": parent_issue,
            "authoritative_repo": self.authoritative_repo,
            "target": target,
            "capability": capability,
            "authority": "Gene 0",
            "closure_authority": "Gene 0",
            "challenge_mode": bool(challenge_mode),
        }
        lease: PeerWorkLease = self.peer_compute.lease(
            task_id,
            peer,
            capability,
            payload,
            max_seconds=self.lease_seconds,
        )
        record = DelegatedWork(
            task_id=task_id,
            parent_issue=parent_issue,
            authoritative_repo=self.authoritative_repo,
            target=target,
            capability=capability,
            peer_logical_id=peer,
            lease=lease.as_dict(),
            created_at=now.isoformat(),
            expires_at=(now + timedelta(seconds=self.lease_seconds)).isoformat(),
            challenge_mode=bool(challenge_mode),
        )
        rows = self._load()
        rows.append(record.as_dict())
        self._save(rows)

        message = self.peer_network.send_message(
            "gene-node-1",
            peer,
            subject=f"Delegated support for authoritative Issue #{parent_issue}",
            body=json.dumps(
                {
                    "lease": lease.as_dict(),
                    "payload": payload,
                    "rules": {
                        "authoritative_parent_remains_gene0": True,
                        "peer_may_not_close_parent": True,
                        "result_requires_signed_message": True,
                        "gene0_validation_required": True,
                        "exact_promotion_rules_preserved": True,
                    },
                },
                sort_keys=True,
            ),
            message_type="delegated_work_lease",
        )
        self._audit(
            "delegated",
            parent_issue=parent_issue,
            peer=peer,
            capability=capability,
            target=target,
            task_id=task_id,
            message_id=message.get("message_id"),
        )
        return {
            "status": "delegated",
            "task": record.as_dict(),
            "message": message,
        }

    def ingest_result(
        self,
        *,
        signed_message: dict[str, Any],
        output: Any,
        claimed_output_hash: str,
        independently_validated: bool,
    ) -> dict[str, Any]:
        if not self.peer_network.verify_message(signed_message):
            self._audit("result_rejected", reason="invalid_signature")
            return {"status": "rejected", "reason": "invalid_signature"}
        if signed_message.get("message_type") != "delegated_work_result":
            self._audit("result_rejected", reason="wrong_message_type")
            return {"status": "rejected", "reason": "wrong_message_type"}

        try:
            body = json.loads(str(signed_message.get("body") or "{}"))
        except ValueError:
            return {"status": "rejected", "reason": "invalid_result_body"}
        task_id = str(body.get("task_id") or "")
        rows = self._load()
        row = next((item for item in rows if item.get("task_id") == task_id and item.get("status") == "leased"), None)
        if row is None:
            self._audit("result_rejected", task_id=task_id, reason="unknown_or_inactive_lease")
            return {"status": "rejected", "reason": "unknown_or_inactive_lease"}
        if signed_message.get("sender_logical_id") != row.get("peer_logical_id"):
            self._audit("result_rejected", task_id=task_id, reason="wrong_peer")
            return {"status": "rejected", "reason": "wrong_peer"}

        lease = PeerWorkLease(**row["lease"])
        verification = self.peer_compute.verify_result(lease, output, claimed_output_hash)
        if not verification.verified:
            self._audit("result_rejected", task_id=task_id, reason="output_hash_mismatch")
            return {"status": "rejected", "reason": "output_hash_mismatch"}
        if not independently_validated:
            self._audit("result_rejected", task_id=task_id, reason="independent_validation_required")
            return {"status": "rejected", "reason": "independent_validation_required"}

        for item in rows:
            if item.get("task_id") == task_id and item.get("status") == "leased":
                item["status"] = "accepted_evidence"
                item["result_message_id"] = signed_message.get("message_id")
                item["result_hash"] = verification.output_hash
        self._save(rows)
        self._audit(
            "result_accepted",
            task_id=task_id,
            parent_issue=row.get("parent_issue"),
            peer=row.get("peer_logical_id"),
            output_hash=verification.output_hash,
        )
        return {
            "status": "accepted_evidence",
            "parent_issue": row.get("parent_issue"),
            "task_id": task_id,
            "peer": row.get("peer_logical_id"),
            "output_hash": verification.output_hash,
            "closure_authority": "Gene 0",
            "promotion_authority": "existing_validation_and_exact_promotion_pipeline",
        }

    def reclaim_expired(self, *, now: datetime | None = None) -> list[dict[str, Any]]:
        now = now or self._now()
        rows = self._load()
        reclaimed: list[dict[str, Any]] = []
        changed = False
        for row in rows:
            if row.get("status") != "leased":
                continue
            try:
                expires = datetime.fromisoformat(str(row.get("expires_at") or "").replace("Z", "+00:00"))
            except ValueError:
                expires = now - timedelta(seconds=1)
            if expires.tzinfo is None:
                expires = expires.replace(tzinfo=timezone.utc)
            if expires <= now:
                row["status"] = "reclaimed"
                row["reclaimed_at"] = now.isoformat()
                reclaimed.append(dict(row))
                changed = True
                self._audit(
                    "lease_reclaimed",
                    task_id=row.get("task_id"),
                    parent_issue=row.get("parent_issue"),
                    peer=row.get("peer_logical_id"),
                    fallback="Gene 0 may route locally or lease to another compatible idle Gene",
                )
        if changed:
            self._save(rows)
        return reclaimed
