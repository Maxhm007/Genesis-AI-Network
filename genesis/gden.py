from __future__ import annotations

import base64
import hashlib
import json
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from cryptography.hazmat.primitives.serialization import Encoding, NoEncryption, PrivateFormat, PublicFormat


def _canonical(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class ContributionPolicy:
    max_cpu_percent: int = 10
    max_memory_mb: int = 1024
    max_storage_mb: int = 2048
    allow_research: bool = True
    allow_validation: bool = True
    allow_model_inference: bool = False
    allow_storage: bool = True
    allow_task_execution: bool = True

    def __post_init__(self) -> None:
        if not 0 <= self.max_cpu_percent <= 100:
            raise ValueError("max_cpu_percent must be between 0 and 100")
        for name in ("max_memory_mb", "max_storage_mb"):
            value = getattr(self, name)
            if value < 0:
                raise ValueError(f"{name} cannot be negative")


@dataclass(frozen=True)
class NodeAdvertisement:
    node_id: str
    public_key: str
    constitution_sha256: str
    protocol_version: str
    capabilities: tuple[str, ...]
    contribution_policy: ContributionPolicy
    state_root: str
    created_at: str
    nonce: str

    def unsigned_payload(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["capabilities"] = list(self.capabilities)
        return payload


class NodeIdentity:
    """Local cryptographic node identity.

    Private keys remain local to a node. The public-key hash forms the node ID.
    This identity authenticates peer statements; it does not grant authority to
    modify the Genesis Constitution or bypass validation.
    """

    def __init__(self, private_key: Ed25519PrivateKey) -> None:
        self._private_key = private_key

    @classmethod
    def generate(cls) -> "NodeIdentity":
        return cls(Ed25519PrivateKey.generate())

    @classmethod
    def load_or_create(cls, path: Path) -> "NodeIdentity":
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.is_symlink():
            raise RuntimeError("refusing to load Genesis node identity through a symlink")
        if path.exists():
            try:
                os.chmod(path, 0o600)
            except OSError:
                pass
            raw = base64.b64decode(path.read_text(encoding="utf-8").strip(), validate=True)
            return cls(Ed25519PrivateKey.from_private_bytes(raw))

        identity = cls.generate()
        raw = identity._private_key.private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption())
        encoded = base64.b64encode(raw) + b"\n"
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        try:
            fd = os.open(path, flags, 0o600)
        except FileExistsError:
            # Another local process created the identity between the existence
            # check and the exclusive create. Load that identity rather than
            # overwriting it.
            return cls.load_or_create(path)
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(encoded)
                handle.flush()
                os.fsync(handle.fileno())
        except Exception:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass
            raise
        return identity

    @property
    def public_key_bytes(self) -> bytes:
        return self._private_key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)

    @property
    def public_key_b64(self) -> str:
        return base64.b64encode(self.public_key_bytes).decode("ascii")

    @property
    def node_id(self) -> str:
        return "genesis:node:" + _sha256(self.public_key_bytes)[:32]

    def sign(self, payload: dict[str, Any]) -> str:
        return base64.b64encode(self._private_key.sign(_canonical(payload))).decode("ascii")

    @staticmethod
    def verify(public_key_b64: str, payload: dict[str, Any], signature_b64: str) -> bool:
        try:
            key_bytes = base64.b64decode(public_key_b64, validate=True)
            signature = base64.b64decode(signature_b64, validate=True)
            if len(key_bytes) != 32 or len(signature) != 64:
                return False
            key = Ed25519PublicKey.from_public_bytes(key_bytes)
            key.verify(signature, _canonical(payload))
            return True
        except Exception:
            return False


def make_advertisement(
    identity: NodeIdentity,
    constitution_sha256: str,
    capabilities: list[str] | tuple[str, ...],
    policy: ContributionPolicy,
    state_root: str = "",
    nonce: str | None = None,
) -> dict[str, Any]:
    advertisement = NodeAdvertisement(
        node_id=identity.node_id,
        public_key=identity.public_key_b64,
        constitution_sha256=constitution_sha256,
        protocol_version="gden/0.1",
        capabilities=tuple(sorted(set(capabilities))),
        contribution_policy=policy,
        state_root=state_root,
        created_at=utc_now(),
        nonce=nonce or os.urandom(16).hex(),
    )
    payload = advertisement.unsigned_payload()
    return {"advertisement": payload, "signature": identity.sign(payload)}


def verify_advertisement(
    envelope: dict[str, Any],
    expected_constitution_hash: str,
    expected_nonce: str | None = None,
) -> tuple[bool, str]:
    payload = envelope.get("advertisement")
    signature = envelope.get("signature")
    if not isinstance(payload, dict) or not isinstance(signature, str):
        return False, "malformed"
    public_key = str(payload.get("public_key", ""))
    node_id = str(payload.get("node_id", ""))
    try:
        public_key_bytes = base64.b64decode(public_key, validate=True)
        if len(public_key_bytes) != 32:
            return False, "invalid_public_key"
        derived = "genesis:node:" + _sha256(public_key_bytes)[:32]
    except Exception:
        return False, "invalid_public_key"
    if node_id != derived:
        return False, "node_id_mismatch"
    if payload.get("constitution_sha256") != expected_constitution_hash:
        return False, "constitution_mismatch"
    if payload.get("protocol_version") != "gden/0.1":
        return False, "protocol_mismatch"
    if expected_nonce is not None and payload.get("nonce") != expected_nonce:
        return False, "challenge_mismatch"
    if not NodeIdentity.verify(public_key, payload, signature):
        return False, "invalid_signature"
    return True, "authenticated"


@dataclass(frozen=True)
class LedgerEntry:
    index: int
    previous_hash: str
    event_type: str
    payload_hash: str
    signer_node_id: str
    signer_public_key: str
    created_at: str
    signature: str

    def signing_payload(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "previous_hash": self.previous_hash,
            "event_type": self.event_type,
            "payload_hash": self.payload_hash,
            "signer_node_id": self.signer_node_id,
            "signer_public_key": self.signer_public_key,
            "created_at": self.created_at,
        }

    @property
    def entry_hash(self) -> str:
        return _sha256(_canonical(asdict(self)))


class EvolutionLedger:
    """Append-only signed hash chain for GDEN evolution proofs.

    This is the blockchain-style provenance layer, not a cryptocurrency and not
    proof-of-work. Consensus/replication across independent nodes is a separate
    layer; the local chain makes tampering and history divergence detectable.
    """

    def __init__(self, path: Path) -> None:
        self.path = path

    def entries(self) -> list[LedgerEntry]:
        if not self.path.exists():
            return []
        items: list[LedgerEntry] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                items.append(LedgerEntry(**json.loads(line)))
        return items

    def head(self) -> str:
        items = self.entries()
        return items[-1].entry_hash if items else "0" * 64

    def append(self, identity: NodeIdentity, event_type: str, payload: dict[str, Any]) -> LedgerEntry:
        items = self.entries()
        signing = {
            "index": len(items),
            "previous_hash": items[-1].entry_hash if items else "0" * 64,
            "event_type": event_type,
            "payload_hash": _sha256(_canonical(payload)),
            "signer_node_id": identity.node_id,
            "signer_public_key": identity.public_key_b64,
            "created_at": utc_now(),
        }
        entry = LedgerEntry(**signing, signature=identity.sign(signing))
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(asdict(entry), sort_keys=True) + "\n")
        return entry

    def verify(self) -> tuple[bool, str]:
        previous = "0" * 64
        for expected_index, entry in enumerate(self.entries()):
            if entry.index != expected_index:
                return False, "index_mismatch"
            if entry.previous_hash != previous:
                return False, "chain_mismatch"
            try:
                key_bytes = base64.b64decode(entry.signer_public_key, validate=True)
                if len(key_bytes) != 32:
                    return False, "invalid_public_key"
                derived = "genesis:node:" + _sha256(key_bytes)[:32]
            except Exception:
                return False, "invalid_public_key"
            if derived != entry.signer_node_id:
                return False, "signer_mismatch"
            if not NodeIdentity.verify(entry.signer_public_key, entry.signing_payload(), entry.signature):
                return False, "invalid_signature"
            previous = entry.entry_hash
        return True, "valid"
