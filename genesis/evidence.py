from __future__ import annotations

from dataclasses import dataclass, asdict


@dataclass(frozen=True)
class EvidenceRecord:
    claim: str
    source: str
    provenance: str
    confidence: float
    status: str = "candidate"

    def as_dict(self) -> dict:
        return asdict(self)


class EvidenceModule:
    """Create provenance-aware evidence records for scientific and system claims."""

    VALID_STATES = {"candidate", "reviewed", "validated", "rejected", "contradicted"}

    def record(self, claim: str, source: str, provenance: str, confidence: float = 0.0) -> EvidenceRecord:
        if not claim.strip() or not source.strip() or not provenance.strip():
            raise ValueError("claim, source and provenance are required")
        return EvidenceRecord(claim.strip(), source.strip(), provenance.strip(), max(0.0, min(1.0, float(confidence))))

    def transition(self, record: EvidenceRecord, status: str, confidence: float | None = None) -> EvidenceRecord:
        if status not in self.VALID_STATES:
            raise ValueError("unknown evidence state")
        if record.status == "candidate" and status not in {"reviewed", "rejected", "contradicted"}:
            raise ValueError("candidate evidence must be reviewed before validation")
        if record.status == "reviewed" and status not in {"validated", "rejected", "contradicted"}:
            raise ValueError("reviewed evidence must be resolved")
        value = record.confidence if confidence is None else max(0.0, min(1.0, float(confidence)))
        return EvidenceRecord(record.claim, record.source, record.provenance, value, status)
