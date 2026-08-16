from __future__ import annotations

import json
from pathlib import Path

from genesis.gden import (
    ContributionPolicy,
    EvolutionLedger,
    NodeIdentity,
    make_advertisement,
    verify_advertisement,
)
from genesis.gden_peers import GDENPeerClient
from genesis.peers import PeerStatusServer


def test_node_identity_persists(tmp_path: Path):
    path = tmp_path / "node.key"
    first = NodeIdentity.load_or_create(path)
    second = NodeIdentity.load_or_create(path)
    assert first.node_id == second.node_id
    assert first.public_key_b64 == second.public_key_b64


def test_signed_advertisement_authenticates_and_detects_tampering():
    identity = NodeIdentity.generate()
    constitution = "a" * 64
    envelope = make_advertisement(
        identity,
        constitution,
        ["research", "validation"],
        ContributionPolicy(max_cpu_percent=15),
        state_root="b" * 64,
        nonce="test-nonce",
    )
    valid, status = verify_advertisement(envelope, constitution)
    assert valid is True
    assert status == "authenticated"

    tampered = json.loads(json.dumps(envelope))
    tampered["advertisement"]["state_root"] = "c" * 64
    valid, status = verify_advertisement(tampered, constitution)
    assert valid is False
    assert status == "invalid_signature"


def test_constitution_mismatch_is_rejected_before_peer_trust():
    identity = NodeIdentity.generate()
    envelope = make_advertisement(identity, "b" * 64, [], ContributionPolicy())
    valid, status = verify_advertisement(envelope, "a" * 64)
    assert valid is False
    assert status == "constitution_mismatch"


def test_contribution_policy_enforces_bounds():
    try:
        ContributionPolicy(max_cpu_percent=101)
    except ValueError as exc:
        assert "max_cpu_percent" in str(exc)
    else:
        raise AssertionError("invalid contribution policy should be rejected")


def test_evolution_ledger_detects_chain_tampering(tmp_path: Path):
    identity = NodeIdentity.generate()
    path = tmp_path / "ledger.jsonl"
    ledger = EvolutionLedger(path)
    ledger.append(identity, "candidate_observed", {"candidate": "abc"})
    ledger.append(identity, "benchmark_recorded", {"score": 7})
    assert ledger.verify() == (True, "valid")

    lines = path.read_text(encoding="utf-8").splitlines()
    second = json.loads(lines[1])
    second["previous_hash"] = "0" * 64
    lines[1] = json.dumps(second)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    assert ledger.verify()[0] is False


def test_authenticated_peer_probe():
    identity = NodeIdentity.generate()
    constitution = "a" * 64
    policy = ContributionPolicy(max_cpu_percent=20, allow_model_inference=False)

    server = PeerStatusServer(
        "127.0.0.1",
        0,
        lambda: {"node_id": identity.node_id, "constitution_sha256": constitution},
        handshake_factory=lambda: make_advertisement(
            identity,
            constitution,
            ["research", "validation"],
            policy,
            state_root="d" * 64,
        ),
    )
    server.start()
    try:
        host, port = server.address
        record = GDENPeerClient(timeout=2).probe(f"http://{host}:{port}", constitution)
        assert record.status == "authenticated"
        assert record.node_id == identity.node_id
        assert record.state_root == "d" * 64
        assert record.contribution_policy["max_cpu_percent"] == 20
        assert "research" in record.capabilities
    finally:
        server.stop()
