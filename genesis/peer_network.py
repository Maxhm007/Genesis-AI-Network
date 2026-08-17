from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .gden import NodeIdentity


def _canonical(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _sha256(payload: dict[str, Any]) -> str:
    return hashlib.sha256(_canonical(payload)).hexdigest()


@dataclass(frozen=True)
class PeerMessage:
    message_id: str
    sender_logical_id: str
    sender_node_id: str
    sender_public_key: str
    recipient_logical_id: str
    message_type: str
    subject: str
    body: str
    created_at: str
    signature: str

    def signing_payload(self) -> dict[str, Any]:
        return {
            "message_id": self.message_id,
            "sender_logical_id": self.sender_logical_id,
            "sender_node_id": self.sender_node_id,
            "sender_public_key": self.sender_public_key,
            "recipient_logical_id": self.recipient_logical_id,
            "message_type": self.message_type,
            "subject": self.subject,
            "body": self.body,
            "created_at": self.created_at,
        }


@dataclass(frozen=True)
class KnowledgePacket:
    packet_id: str
    author_logical_id: str
    author_node_id: str
    author_public_key: str
    topic: str
    claim: str
    evidence: dict[str, Any]
    provenance: dict[str, Any]
    created_at: str
    signature: str

    def signing_payload(self) -> dict[str, Any]:
        return {
            "packet_id": self.packet_id,
            "author_logical_id": self.author_logical_id,
            "author_node_id": self.author_node_id,
            "author_public_key": self.author_public_key,
            "topic": self.topic,
            "claim": self.claim,
            "evidence": self.evidence,
            "provenance": self.provenance,
            "created_at": self.created_at,
        }


class GenePeerNetwork:
    """Local authenticated communication and selective knowledge sharing for Gene nodes.

    Nodes remain independent. A shared packet is evidence, not authority: each
    recipient records its own adoption/challenge/rejection decision. This avoids
    forcing all Gene replicas into identical state while allowing rapid transfer
    of useful validated learning.
    """

    def __init__(self, root: Path) -> None:
        self.root = Path(root).resolve()
        self.runtime_root = self.root / "runtime" / "grce"
        self.bus_root = self.runtime_root / "peer_bus"
        self.bus_root.mkdir(parents=True, exist_ok=True)

    def _node_root(self, logical_id: str) -> Path:
        path = self.runtime_root / logical_id
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _identity(self, logical_id: str) -> NodeIdentity:
        return NodeIdentity.load_or_create(self._node_root(logical_id) / "identity.key")

    def _inbox(self, logical_id: str) -> Path:
        path = self._node_root(logical_id) / "inbox.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    @staticmethod
    def _append(path: Path, payload: dict[str, Any]) -> None:
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, sort_keys=True) + "\n")

    def send_message(
        self,
        sender_logical_id: str,
        recipient_logical_id: str,
        subject: str,
        body: str,
        message_type: str = "peer_conversation",
    ) -> dict[str, Any]:
        identity = self._identity(sender_logical_id)
        created_at = datetime.now(timezone.utc).isoformat()
        unsigned = {
            "sender_logical_id": sender_logical_id,
            "sender_node_id": identity.node_id,
            "sender_public_key": identity.public_key_b64,
            "recipient_logical_id": recipient_logical_id,
            "message_type": message_type,
            "subject": subject,
            "body": body,
            "created_at": created_at,
        }
        message_id = _sha256(unsigned)[:24]
        signing = {"message_id": message_id, **unsigned}
        message = PeerMessage(**signing, signature=identity.sign(signing))
        payload = asdict(message)
        self._append(self._inbox(recipient_logical_id), payload)
        return payload

    @staticmethod
    def verify_message(payload: dict[str, Any]) -> bool:
        try:
            message = PeerMessage(**payload)
        except Exception:
            return False
        return NodeIdentity.verify(message.sender_public_key, message.signing_payload(), message.signature)

    def receive_messages(self, logical_id: str, verified_only: bool = True) -> list[dict[str, Any]]:
        path = self._inbox(logical_id)
        if not path.exists():
            return []
        messages = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        if verified_only:
            messages = [item for item in messages if self.verify_message(item)]
        return messages

    def publish_knowledge(
        self,
        author_logical_id: str,
        topic: str,
        claim: str,
        evidence: dict[str, Any],
        provenance: dict[str, Any],
    ) -> dict[str, Any]:
        identity = self._identity(author_logical_id)
        created_at = datetime.now(timezone.utc).isoformat()
        unsigned = {
            "author_logical_id": author_logical_id,
            "author_node_id": identity.node_id,
            "author_public_key": identity.public_key_b64,
            "topic": topic,
            "claim": claim,
            "evidence": dict(evidence),
            "provenance": dict(provenance),
            "created_at": created_at,
        }
        packet_id = _sha256(unsigned)[:24]
        signing = {"packet_id": packet_id, **unsigned}
        packet = KnowledgePacket(**signing, signature=identity.sign(signing))
        payload = asdict(packet)
        packet_path = self.bus_root / "knowledge.jsonl"
        self._append(packet_path, payload)
        return payload

    @staticmethod
    def verify_knowledge(payload: dict[str, Any]) -> bool:
        try:
            packet = KnowledgePacket(**payload)
        except Exception:
            return False
        return NodeIdentity.verify(packet.author_public_key, packet.signing_payload(), packet.signature)

    def knowledge_feed(self, topic: str | None = None) -> list[dict[str, Any]]:
        path = self.bus_root / "knowledge.jsonl"
        if not path.exists():
            return []
        packets = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        packets = [item for item in packets if self.verify_knowledge(item)]
        if topic is not None:
            packets = [item for item in packets if item.get("topic") == topic]
        return packets

    def record_knowledge_decision(
        self,
        logical_id: str,
        packet_id: str,
        decision: str,
        reason: str,
    ) -> dict[str, Any]:
        if decision not in {"adopt", "challenge", "reject", "defer"}:
            raise ValueError("decision must be adopt, challenge, reject, or defer")
        identity = self._identity(logical_id)
        payload = {
            "logical_id": logical_id,
            "node_id": identity.node_id,
            "packet_id": packet_id,
            "decision": decision,
            "reason": reason,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        payload["signature"] = identity.sign(dict(payload))
        self._append(self._node_root(logical_id) / "knowledge_decisions.jsonl", payload)
        return payload

    def status(self, logical_ids: tuple[str, ...] = ("gene-node-2", "gene-node-3", "gene-node-4", "gene-node-5")) -> dict[str, Any]:
        return {
            "protocol": "gene-peer/0.1",
            "communication": "authenticated_any_gene_to_any_gene",
            "knowledge_model": "signed_share_selective_adoption",
            "independent_evolution": True,
            "nodes": {
                logical_id: {
                    "node_id": self._identity(logical_id).node_id,
                    "inbox_messages": len(self.receive_messages(logical_id)),
                    "decision_log": str(self._node_root(logical_id) / "knowledge_decisions.jsonl"),
                }
                for logical_id in logical_ids
                if self._node_root(logical_id).exists()
            },
            "knowledge_packets": len(self.knowledge_feed()),
        }
