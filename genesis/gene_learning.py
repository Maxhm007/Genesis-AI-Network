from __future__ import annotations

from pathlib import Path
from typing import Any

from .gene_names import identity_for_logical_id
from .peer_network import GenePeerNetwork
from .self_learning import LearningLesson, SelfLearningStore


def _gene_name(logical_id: str) -> str:
    return identity_for_logical_id(logical_id).display_name


class GeneLearningEngine:
    """Independent learning memory for one Gene instance.

    Every Gene writes to its own store under runtime/grce/<logical_id>/learning.sqlite3.
    Lessons remain local unless explicitly validated and shared. Peer lessons are
    advisory evidence and are imported as candidates so each Gene can independently
    adopt, challenge, reject, or defer them.
    """

    def __init__(self, root: Path, logical_id: str) -> None:
        self.root = Path(root).resolve()
        self.logical_id = logical_id
        self.node_root = self.root / "runtime" / "grce" / logical_id
        self.node_root.mkdir(parents=True, exist_ok=True)
        self.store = SelfLearningStore(self.node_root / "learning.sqlite3")
        self.peers = GenePeerNetwork(self.root)

    def add_candidate(
        self,
        *,
        source_type: str,
        source_ref: str,
        topic: str,
        lesson: str,
        evidence: dict[str, Any] | None = None,
        confidence: float = 0.5,
    ) -> LearningLesson:
        return self.store.add_candidate(
            source_type=source_type,
            source_ref=source_ref,
            topic=topic,
            lesson=lesson,
            evidence={"gene": _gene_name(self.logical_id), **dict(evidence or {})},
            confidence=confidence,
        )

    def validate(self, lesson_id: str, evidence: dict[str, Any]) -> LearningLesson:
        return self.store.transition(lesson_id, "validated", validation_evidence=evidence)

    def reject(self, lesson_id: str, evidence: dict[str, Any] | None = None) -> LearningLesson:
        return self.store.transition(lesson_id, "rejected", validation_evidence=evidence)

    def share_validated(self, lesson_id: str) -> dict[str, Any]:
        lesson = self.store.get(lesson_id)
        if lesson is None:
            raise KeyError(lesson_id)
        if lesson.state != "validated":
            raise ValueError("only validated lessons may be shared with peer Genes")
        return self.peers.publish_knowledge(
            self.logical_id,
            topic=f"learning:{lesson.topic}",
            claim=lesson.lesson,
            evidence={
                "lesson_id": lesson.lesson_id,
                "confidence": lesson.confidence,
                "validation": lesson.evidence.get("validation"),
                "source_type": lesson.source_type,
                "source_ref": lesson.source_ref,
            },
            provenance={
                "author_gene": _gene_name(self.logical_id),
                "learning_state": lesson.state,
                "rule": "validated_lessons_only",
            },
        )

    def import_peer_packet(self, packet: dict[str, Any]) -> LearningLesson:
        if not self.peers.verify_knowledge(packet):
            raise ValueError("invalid peer knowledge signature")
        provenance = dict(packet.get("provenance") or {})
        if provenance.get("learning_state") != "validated":
            raise ValueError("peer learning packet is not validated")
        author = str(packet.get("author_logical_id"))
        packet_id = str(packet.get("packet_id"))
        return self.add_candidate(
            source_type="peer_validated_learning",
            source_ref=f"{author}:{packet_id}",
            topic=str(packet.get("topic", "peer learning")),
            lesson=str(packet.get("claim", "")),
            evidence={
                "peer_packet": packet,
                "peer_author": _gene_name(author),
                "rule": "import_as_candidate_not_authority",
            },
            confidence=float((packet.get("evidence") or {}).get("confidence", 0.5)),
        )

    def status(self) -> dict[str, Any]:
        return {
            "gene": _gene_name(self.logical_id),
            "logical_id": self.logical_id,
            "store": str(self.node_root / "learning.sqlite3"),
            "candidate": len(self.store.list(state="candidate", limit=10000)),
            "validated": len(self.store.list(state="validated", limit=10000)),
            "rejected": len(self.store.list(state="rejected", limit=10000)),
            "sharing_rule": "validated_only",
            "peer_import_rule": "candidate_then_independent_validation",
        }
