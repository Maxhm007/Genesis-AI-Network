from __future__ import annotations

import base64
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def attestation_material(attestation: dict) -> dict:
    """Canonical signed GDEN attestation payload.

    Signature metadata is intentionally excluded. Every field that establishes
    peer identity, network membership and the claimed chain state is covered.
    """
    return {
        "network": str(attestation.get("network", "")).strip(),
        "peer_id": str(attestation.get("peer_id", "")).strip(),
        "repository": str(attestation.get("repository", "")).strip(),
        "genesis_anchor": str(attestation.get("genesis_anchor", "")).strip(),
        "height": int(attestation.get("height", -1)),
        "head": str(attestation.get("head", "")).strip(),
        "observed_at": str(attestation.get("observed_at", "")).strip(),
    }


def _parse_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def verify_ed25519_attestation(
    attestation: dict,
    public_key_b64: str,
    *,
    max_age_seconds: int = 7200,
    now: datetime | None = None,
) -> tuple[bool, str]:
    """Verify one persistent-key attestation and return a stable rejection reason."""
    if attestation.get("signature_algorithm") != "ed25519":
        return False, "missing_or_wrong_signature_algorithm"
    signature_b64 = str(attestation.get("signature", "")).strip()
    if not signature_b64:
        return False, "missing_signature"
    try:
        material = attestation_material(attestation)
    except (TypeError, ValueError):
        return False, "malformed_attestation"
    if not material["observed_at"]:
        return False, "missing_observed_at"
    try:
        observed = _parse_time(material["observed_at"])
    except ValueError:
        return False, "invalid_observed_at"
    current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    age = (current - observed).total_seconds()
    if age < -300:
        return False, "attestation_from_future"
    if max_age_seconds >= 0 and age > max_age_seconds:
        return False, "stale_attestation"
    try:
        public_key = Ed25519PublicKey.from_public_bytes(base64.b64decode(public_key_b64, validate=True))
        signature = base64.b64decode(signature_b64, validate=True)
        public_key.verify(signature, canonical_json(material).encode("utf-8"))
    except (ValueError, InvalidSignature):
        return False, "invalid_signature"
    return True, "verified"


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
    commitments only. Repository agreement and persistent-key cryptographic
    quorum are reported separately so Genesis cannot overstate decentralization.
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

    def consensus_status(
        self,
        peer_attestations: list[dict] | None = None,
        *,
        trusted_peers: dict[str, str] | None = None,
        trusted_peer_keys: dict[str, str] | None = None,
        max_attestation_age_seconds: int = 7200,
        now: datetime | None = None,
    ) -> dict:
        """Return local-chain, repository-agreement and cryptographic quorum state.

        ``trusted_peer_keys is None`` preserves legacy repository-quorum semantics
        for internal callers. Supplying a mapping, including an empty mapping,
        makes persistent Ed25519 verification mandatory for ``consensus_active``.
        """
        verification = self.verify()
        head = verification.get("head")
        genesis_anchor = verification.get("genesis_anchor")
        height = int(verification.get("height", 0))
        cryptographic_required = trusted_peer_keys is not None
        unique_peers: set[str] = set()
        repository_matching = 0
        cryptographic_matching = 0
        rejected: list[dict[str, str]] = []

        for attestation in peer_attestations or []:
            peer_id = str(attestation.get("peer_id", "")).strip()
            peer_head = str(attestation.get("head", "")).strip()
            repository = str(attestation.get("repository", "")).strip()
            network = str(attestation.get("network", "")).strip()
            attested_anchor = str(attestation.get("genesis_anchor", "")).strip()
            try:
                attested_height = int(attestation.get("height", -1))
            except (TypeError, ValueError):
                attested_height = -1

            reason = None
            if not peer_id:
                reason = "missing_peer_id"
            elif peer_id in unique_peers:
                reason = "duplicate_peer"
            elif peer_head != head:
                reason = "wrong_head"
            elif cryptographic_required and attested_height != height:
                reason = "wrong_height"
            elif trusted_peers is not None:
                expected_repository = trusted_peers.get(peer_id)
                if not expected_repository or repository != expected_repository:
                    reason = "wrong_repository"
                elif network != "gden/0.1":
                    reason = "wrong_network"
                elif attested_anchor != genesis_anchor:
                    reason = "wrong_genesis_anchor"

            if reason:
                rejected.append({"peer_id": peer_id or "unknown", "reason": reason})
                continue

            unique_peers.add(peer_id)
            repository_matching += 1

            if not cryptographic_required:
                continue

            public_key = trusted_peer_keys.get(peer_id)
            if not public_key:
                rejected.append({"peer_id": peer_id, "reason": "untrusted_or_missing_public_key"})
                continue
            valid_signature, signature_reason = verify_ed25519_attestation(
                attestation,
                public_key,
                max_age_seconds=max_attestation_age_seconds,
                now=now,
            )
            if not valid_signature:
                rejected.append({"peer_id": peer_id, "reason": signature_reason})
                continue
            cryptographic_matching += 1

        chain_valid = bool(verification.get("valid"))
        repository_active = chain_valid and repository_matching >= self.quorum
        active = chain_valid and (
            cryptographic_matching >= self.quorum if cryptographic_required else repository_active
        )
        return {
            "module": "genesis.blockchain",
            "chain_valid": chain_valid,
            "height": height,
            "head": head,
            "genesis_anchor": genesis_anchor,
            "repository_matching_peers": repository_matching,
            "repository_consensus_active": repository_active,
            "matching_independent_peers": cryptographic_matching if cryptographic_required else repository_matching,
            "cryptographic_matching_peers": cryptographic_matching if cryptographic_required else 0,
            "cryptographic_verification_required": cryptographic_required,
            "rejected_attestations": len(rejected),
            "rejection_details": rejected,
            "required_quorum": self.quorum,
            "consensus_active": active,
            "status": "consensus_active" if active else "local_chain_active_consensus_pending",
            "large_data_on_chain": False,
        }
