from __future__ import annotations

import hashlib
import json
from pathlib import Path

from genesis.gene_care import GeneCareNetwork, GeneHealth
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


def test_gene_can_detect_peer_needs_care_and_offer_help(tmp_path: Path) -> None:
    root = _root(tmp_path)
    care = GeneCareNetwork(root)
    health = GeneHealth("gene-node-3", status="degraded", error_count=2)
    assert health.needs_care()
    result = care.care_for("gene-node-2", health, "provider failure", "switch provider and rerun validation")
    assert result["status"] == "care_offered"
    inbox = GenePeerNetwork(root).receive_messages("gene-node-3")
    assert inbox[-1]["message_type"] == "care_offer"


def test_gene_can_share_repair_without_forcing_adoption(tmp_path: Path) -> None:
    root = _root(tmp_path)
    care = GeneCareNetwork(root)
    packet = care.record_repair_proposal(
        "gene-node-4",
        "gene-node-3",
        "repair loop failing",
        "retry with bounded fallback",
        {"reproduced": True},
    )
    assert packet["topic"] == "gene-care"
    decisions = root / "runtime/grce/gene-node-3/knowledge_decisions.jsonl"
    assert not decisions.exists(), "repair proposals must not be auto-adopted"


def test_gene_verifies_peer_recovery(tmp_path: Path) -> None:
    root = _root(tmp_path)
    care = GeneCareNetwork(root)
    result = care.verify_recovery(
        "gene-node-2",
        GeneHealth("gene-node-3", status="healthy"),
        {"tests": "pass", "provider": "healthy"},
    )
    assert result["recovered"] is True
    assert (root / "runtime/grce/gene-node-2/care.jsonl").exists()
