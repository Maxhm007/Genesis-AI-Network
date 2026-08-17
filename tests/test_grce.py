from __future__ import annotations

import hashlib
import json
from pathlib import Path

from genesis.gden import EvolutionLedger, verify_advertisement
from genesis.grce import GeneFederation


def _root(tmp_path: Path) -> Path:
    root = tmp_path / "gene"
    root.mkdir()
    constitution = b"# Test Constitution\n"
    (root / "GENESIS_CONSTITUTION.md").write_bytes(constitution)
    digest = hashlib.sha256(constitution).hexdigest()
    (root / "GENESIS_BLOCK.json").write_text(
        json.dumps({"constitution": {"sha256": digest}}), encoding="utf-8"
    )
    return root


def test_provisions_nodes_2_and_3_with_isolated_identity_and_state(tmp_path: Path) -> None:
    root = _root(tmp_path)
    federation = GeneFederation(root)
    nodes = federation.provision()

    assert [item["logical_id"] for item in nodes] == ["gene-node-2", "gene-node-3"]
    assert nodes[0]["node_id"] != nodes[1]["node_id"]
    assert nodes[0]["constitution_sha256"] == nodes[1]["constitution_sha256"]
    assert nodes[0]["replication_policy"] == "authorized_specs_only"

    for item in nodes:
        child_root = root / "runtime" / "grce" / item["logical_id"]
        assert (child_root / "identity.key").exists()
        assert (child_root / "manifest.json").exists()
        ok, reason = verify_advertisement(item["advertisement"], item["constitution_sha256"])
        assert ok is True, reason
        ledger = EvolutionLedger(child_root / "evolution_ledger.jsonl")
        assert ledger.verify() == (True, "valid")


def test_reprovision_keeps_child_node_identities_stable(tmp_path: Path) -> None:
    root = _root(tmp_path)
    federation = GeneFederation(root)
    first = federation.provision()
    second = federation.provision()
    assert [item["node_id"] for item in first] == [item["node_id"] for item in second]


def test_status_exposes_distinct_cooperative_roles(tmp_path: Path) -> None:
    root = _root(tmp_path)
    federation = GeneFederation(root)
    federation.provision()
    status = federation.status()
    roles = {item["logical_id"]: item["role"] for item in status["children"]}
    assert status["protocol"] == "grce/0.1"
    assert roles == {
        "gene-node-2": "explorer_researcher",
        "gene-node-3": "engineer_challenger",
    }
