from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, asdict


@dataclass(frozen=True)
class PeerWorkLease:
    task_id: str
    peer_id: str
    capability: str
    input_hash: str
    max_seconds: int

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class PeerWorkResult:
    task_id: str
    peer_id: str
    output_hash: str
    verified: bool

    def as_dict(self) -> dict:
        return asdict(self)


class PeerComputeModule:
    """Bounded GDEN work leasing and result-hash verification primitives."""

    @staticmethod
    def hash_payload(payload: object) -> str:
        raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        return hashlib.sha256(raw).hexdigest()

    def lease(self, task_id: str, peer_id: str, capability: str, payload: object, max_seconds: int = 300) -> PeerWorkLease:
        if not task_id.strip() or not peer_id.strip() or not capability.strip():
            raise ValueError("task_id, peer_id and capability are required")
        if max_seconds <= 0 or max_seconds > 3600:
            raise ValueError("peer work lease must be between 1 and 3600 seconds")
        return PeerWorkLease(task_id.strip(), peer_id.strip(), capability.strip(), self.hash_payload(payload), int(max_seconds))

    def verify_result(self, lease: PeerWorkLease, output: object, claimed_output_hash: str) -> PeerWorkResult:
        actual = self.hash_payload(output)
        return PeerWorkResult(lease.task_id, lease.peer_id, actual, actual == claimed_output_hash)
