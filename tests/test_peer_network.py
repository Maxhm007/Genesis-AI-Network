from __future__ import annotations

import hashlib
import json
from pathlib import Path

from genesis.peer_network import GenePeerNetwork


def _root(tmp_path: Path) -> Path:
    root = tmp_path / "gene"
    root.mkdir()
    constitution = b"# Test Constitution\n"
    (root / "GENESIS_CONSTITUTION.md").write_bytes(constitution)
    (root / "GENESIS_BLOCK.json").write_text(
        json.dumps({"constitution": {"sha256": hashlib.sha256(constitution).hexdigest()}}), encoding="utf-8"
    )
    return root


def test_any_gene_can_send_authenticated_message_to_another(tmp_path: Path) -> None:
    network = GenePeerNetwork(_root(tmp_path))
    sent = network.send_message("gene-node-2", "gene-node-5", "Need evidence", "Share your latest repair benchmark")
    inbox = network.receive_messages("gene-node-5")
    assert len(inbox) == 1
    assert inbox[0]["message_id"] == sent["message_id"]
    assert inbox[0]["sender_logical_id"] == "gene-node-2"
    assert network.verify_message(inbox[0])


def test_knowledge_is_signed_and_selectively_adopted(tmp_path: Path) -> None:
    network = GenePeerNetwork(_root(tmp_path))
    packet = network.publish_knowledge(
        "gene-node-4",
        topic="provider-routing",
        claim="Candidate routing change reduced retry count in local test",
        evidence={"retry_before": 4, "retry_after": 2},
        provenance={"test": "local"},
    )
    assert network.verify_knowledge(packet)
    assert network.knowledge_feed("provider-routing")[0]["packet_id"] == packet["packet_id"]

    node2 = network.record_knowledge_decision("gene-node-2", packet["packet_id"], "adopt", "reproduced locally")
    node3 = network.record_knowledge_decision("gene-node-3", packet["packet_id"], "challenge", "needs adversarial test")
    assert node2["decision"] == "adopt"
    assert node3["decision"] == "challenge"


def test_tampered_message_is_rejected(tmp_path: Path) -> None:
    network = GenePeerNetwork(_root(tmp_path))
    sent = network.send_message("gene-node-3", "gene-node-4", "Review", "Original")
    sent["body"] = "Tampered"
    assert not network.verify_message(sent)


def test_peer_status_declares_independent_evolution(tmp_path: Path) -> None:
    network = GenePeerNetwork(_root(tmp_path))
    status = network.status(("gene-node-2", "gene-node-3"))
    assert status["independent_evolution"] is True
    assert status["communication"] == "authenticated_any_gene_to_any_gene"
    assert status["knowledge_model"] == "signed_share_selective_adoption"
