from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ChainBlock:
    height: int
    timestamp: str
    previous_hash: str
    payload_hash: str
    payload_type: str
    producer: str
    block_hash: str

    def as_dict(self) -> dict:
        return asdict(self)


class BlockchainModule:
    """Compact tamper-evident Genesis commitment chain.

    Large data stays off-chain. This module stores hashes and compact state
    commitments only. It is a working local append-only chain, not a claim of
    network consensus. Consensus becomes active only after independent peers
    attest to the same chain head with the configured quorum.
    """

    def __init__(self, root: Path, quorum: int = 2) -> None:
        self.root = Path(root).resolve()
        self.runtime = self.root / "runtime"
        self.runtime.mkdir(parents=True, exist_ok=True)
        self.chain_path = self.runtime / "blockchain.jsonl"
        self.quorum = max(2, int(quorum))

    def _genesis_anchor(self) -> str:
        path = self.root / "GENESIS_BLOCK.json"
        if not path.is_file():
            raise FileNotFoundError("GENESIS_BLOCK.json is required")
        return sha256_text(path.read_text(encoding="utf-8"))

    def _load(self) -> list[dict]:
        if not self.chain_path.exists():
            return []
        rows: list[dict] = []
        for line in self.chain_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            rows.append(json.loads(line))
        return rows

    @staticmethod
    def _block_hash(block: dict) -> str:
        material = {
            "height": block["height"],
            "timestamp": block["timestamp"],
            "previous_hash": block["previous_hash"],
            "payload_hash": block["payload_hash"],
            "payload_type": block["payload_type"],
            "producer": block["producer"],
        }
        return sha256_text(canonical_json(material))

    def append_commitment(self, payload: Any, *, payload_type: str, producer: str) -> ChainBlock:
        if not payload_type.strip() or not producer.strip():
            raise ValueError("payload_type and producer are required")
        if not self.verify()["valid"]:
            raise RuntimeError("refusing to append to an invalid chain")
        chain = self._load()
        height = len(chain)
        previous_hash = chain[-1]["block_hash"] if chain else self._genesis_anchor()
        row = {
            "height": height,
            "timestamp": utc_now(),
            "previous_hash": previous_hash,
            "payload_hash": sha256_text(canonical_json(payload)),
            "payload_type": payload_type.strip(),
            "producer": producer.strip(),
        }
        row["block_hash"] = self._block_hash(row)
        with self.chain_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, sort_keys=True) + "\n")
        return ChainBlock(**row)

    def verify(self) -> dict:
        try:
            chain = self._load()
            previous = self._genesis_anchor()
            for expected_height, row in enumerate(chain):
                if int(row.get("height", -1)) != expected_height:
                    return {"valid": False, "height": len(chain), "error": "height discontinuity"}
                if row.get("previous_hash") != previous:
                    return {"valid": False, "height": len(chain), "error": "previous hash mismatch"}
                if row.get("block_hash") != self._block_hash(row):
                    return {"valid": False, "height": len(chain), "error": "block hash mismatch"}
                previous = row["block_hash"]
            return {
                "valid": True,
                "height": len(chain),
                "head": previous if chain else self._genesis_anchor(),
                "genesis_anchor": self._genesis_anchor(),
            }
        except Exception as exc:
            return {"valid": False, "height": 0, "error": f"{type(exc).__name__}: {exc}"}

    def consensus_status(self, peer_attestations: list[dict] | None = None) -> dict:
        verification = self.verify()
        head = verification.get("head")
        unique_peers: set[str] = set()
        matching = 0
        for attestation in peer_attestations or []:
            peer_id = str(attestation.get("peer_id", "")).strip()
            peer_head = str(attestation.get("head", "")).strip()
            if peer_id and peer_id not in unique_peers and peer_head == head:
                unique_peers.add(peer_id)
                matching += 1
        active = bool(verification.get("valid")) and matching >= self.quorum
        return {
            "module": "genesis.blockchain",
            "chain_valid": bool(verification.get("valid")),
            "height": verification.get("height", 0),
            "head": head,
            "matching_independent_peers": matching,
            "required_quorum": self.quorum,
            "consensus_active": active,
            "status": "consensus_active" if active else "local_chain_active_consensus_pending",
            "large_data_on_chain": False,
        }
