from __future__ import annotations

import base64
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from genesis.blockchain import BlockchainModule, attestation_material, canonical_json


def _setup(tmp_path: Path) -> BlockchainModule:
    (tmp_path / "GENESIS_BLOCK.json").write_text(json.dumps({"genesis": "test"}), encoding="utf-8")
    return BlockchainModule(tmp_path, quorum=2)


def _keypair() -> tuple[Ed25519PrivateKey, str]:
    private = Ed25519PrivateKey.generate()
    public = private.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return private, base64.b64encode(public).decode("ascii")


def _attestation(chain: BlockchainModule, peer_id: str, repository: str, private: Ed25519PrivateKey, observed_at: str) -> dict:
    state = chain.verify()
    item = {
        "network": "gden/0.1",
        "peer_id": peer_id,
        "repository": repository,
        "genesis_anchor": state["genesis_anchor"],
        "height": state["height"],
        "head": state["head"],
        "observed_at": observed_at,
        "signature_algorithm": "ed25519",
    }
    signature = private.sign(canonical_json(attestation_material(item)).encode("utf-8"))
    item["signature"] = base64.b64encode(signature).decode("ascii")
    return item


def test_two_persistent_keys_activate_cryptographic_quorum(tmp_path: Path) -> None:
    chain = _setup(tmp_path)
    now = datetime.now(timezone.utc)
    key2, pub2 = _keypair()
    key3, pub3 = _keypair()
    attestations = [
        _attestation(chain, "genesis-node-2", "Maxhm007/Genesis-Node-2", key2, now.isoformat()),
        _attestation(chain, "genesis-node-3", "Maxhm007/Genesis-Node-3", key3, now.isoformat()),
    ]
    result = chain.consensus_status(
        attestations,
        trusted_peers={
            "genesis-node-2": "Maxhm007/Genesis-Node-2",
            "genesis-node-3": "Maxhm007/Genesis-Node-3",
        },
        trusted_peer_keys={"genesis-node-2": pub2, "genesis-node-3": pub3},
        now=now,
    )
    assert result["repository_consensus_active"] is True
    assert result["cryptographic_matching_peers"] == 2
    assert result["consensus_active"] is True


def test_unsigned_repository_agreement_does_not_activate_crypto_quorum(tmp_path: Path) -> None:
    chain = _setup(tmp_path)
    now = datetime.now(timezone.utc)
    key2, pub2 = _keypair()
    key3, pub3 = _keypair()
    signed = _attestation(chain, "genesis-node-2", "Maxhm007/Genesis-Node-2", key2, now.isoformat())
    unsigned = _attestation(chain, "genesis-node-3", "Maxhm007/Genesis-Node-3", key3, now.isoformat())
    unsigned.pop("signature")
    result = chain.consensus_status(
        [signed, unsigned],
        trusted_peers={
            "genesis-node-2": "Maxhm007/Genesis-Node-2",
            "genesis-node-3": "Maxhm007/Genesis-Node-3",
        },
        trusted_peer_keys={"genesis-node-2": pub2, "genesis-node-3": pub3},
        now=now,
    )
    assert result["repository_consensus_active"] is True
    assert result["cryptographic_matching_peers"] == 1
    assert result["consensus_active"] is False


def test_signature_cannot_be_reused_after_head_tampering(tmp_path: Path) -> None:
    chain = _setup(tmp_path)
    now = datetime.now(timezone.utc)
    key2, pub2 = _keypair()
    item = _attestation(chain, "genesis-node-2", "Maxhm007/Genesis-Node-2", key2, now.isoformat())
    item["head"] = "tampered"
    result = chain.consensus_status(
        [item],
        trusted_peers={"genesis-node-2": "Maxhm007/Genesis-Node-2"},
        trusted_peer_keys={"genesis-node-2": pub2},
        now=now,
    )
    assert result["consensus_active"] is False
    assert any(row["reason"] == "wrong_head" for row in result["rejection_details"])


def test_stale_signed_attestation_is_rejected(tmp_path: Path) -> None:
    chain = _setup(tmp_path)
    now = datetime.now(timezone.utc)
    key2, pub2 = _keypair()
    item = _attestation(
        chain,
        "genesis-node-2",
        "Maxhm007/Genesis-Node-2",
        key2,
        (now - timedelta(hours=3)).isoformat(),
    )
    result = chain.consensus_status(
        [item],
        trusted_peers={"genesis-node-2": "Maxhm007/Genesis-Node-2"},
        trusted_peer_keys={"genesis-node-2": pub2},
        max_attestation_age_seconds=3600,
        now=now,
    )
    assert result["consensus_active"] is False
    assert any(row["reason"] == "stale_attestation" for row in result["rejection_details"])
