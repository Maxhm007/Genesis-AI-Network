from pathlib import Path

from genesis.blockchain import BlockchainModule
from genesis.updater import UpdaterModule


def make_root(tmp_path: Path) -> Path:
    (tmp_path / "GENESIS_BLOCK.json").write_text('{"genesis": true}\n', encoding="utf-8")
    (tmp_path / "GENESIS_CONSTITUTION.md").write_text("constitution\n", encoding="utf-8")
    return tmp_path


def test_updater_requires_tests_security_quorum_and_protected_boundaries(tmp_path: Path):
    root = make_root(tmp_path)
    updater = UpdaterModule(root)

    approved = updater.evaluate(
        "abc123",
        ["genesis/example.py", "tests/test_example.py"],
        tests_passed=True,
        security_passed=True,
        validator_approvals=2,
    )
    assert approved.eligible is True
    assert approved.status == "eligible_for_protected_promotion"

    blocked = updater.evaluate(
        "abc124",
        ["GENESIS_CONSTITUTION.md"],
        tests_passed=True,
        security_passed=True,
        validator_approvals=2,
    )
    assert blocked.eligible is False
    assert any("protected boundary" in reason for reason in blocked.reasons)


def test_blockchain_appends_and_verifies_commitments(tmp_path: Path):
    root = make_root(tmp_path)
    chain = BlockchainModule(root)
    first = chain.append_commitment({"state_root": "one"}, payload_type="state_root", producer="node-a")
    second = chain.append_commitment({"validation": "pass"}, payload_type="validation", producer="validator-a")

    verification = chain.verify()
    assert verification["valid"] is True
    assert verification["height"] == 2
    assert second.previous_hash == first.block_hash


def test_blockchain_does_not_claim_consensus_without_independent_peer_quorum(tmp_path: Path):
    root = make_root(tmp_path)
    chain = BlockchainModule(root, quorum=2)
    chain.append_commitment({"state_root": "one"}, payload_type="state_root", producer="node-a")
    head = chain.verify()["head"]

    pending = chain.consensus_status([{"peer_id": "peer-1", "head": head}])
    assert pending["consensus_active"] is False
    assert pending["status"] == "local_chain_active_consensus_pending"

    active = chain.consensus_status([
        {"peer_id": "peer-1", "head": head},
        {"peer_id": "peer-2", "head": head},
    ])
    assert active["consensus_active"] is True
    assert active["status"] == "consensus_active"


def test_duplicate_peer_does_not_fake_consensus(tmp_path: Path):
    root = make_root(tmp_path)
    chain = BlockchainModule(root, quorum=2)
    chain.append_commitment({"state_root": "one"}, payload_type="state_root", producer="node-a")
    head = chain.verify()["head"]
    status = chain.consensus_status([
        {"peer_id": "peer-1", "head": head},
        {"peer_id": "peer-1", "head": head},
    ])
    assert status["matching_independent_peers"] == 1
    assert status["consensus_active"] is False


def test_trusted_repository_peers_are_required_for_authenticated_consensus(tmp_path: Path):
    root = make_root(tmp_path)
    chain = BlockchainModule(root, quorum=2)
    verification = chain.verify()
    head = verification["head"]
    anchor = verification["genesis_anchor"]
    trusted = {
        "genesis-node-2": "Maxhm007/Genesis-Node-2",
        "genesis-node-3": "Maxhm007/Genesis-Node-3",
    }
    attestations = [
        {
            "peer_id": "genesis-node-2",
            "repository": "Maxhm007/Genesis-Node-2",
            "network": "gden/0.1",
            "genesis_anchor": anchor,
            "head": head,
        },
        {
            "peer_id": "genesis-node-3",
            "repository": "Maxhm007/Genesis-Node-3",
            "network": "gden/0.1",
            "genesis_anchor": anchor,
            "head": head,
        },
    ]
    active = chain.consensus_status(attestations, trusted_peers=trusted)
    assert active["consensus_active"] is True
    assert active["matching_independent_peers"] == 2

    forged = list(attestations)
    forged[1] = {**forged[1], "repository": "attacker/fake-node"}
    blocked = chain.consensus_status(forged, trusted_peers=trusted)
    assert blocked["consensus_active"] is False
    assert blocked["matching_independent_peers"] == 1
    assert blocked["rejected_attestations"] >= 1
