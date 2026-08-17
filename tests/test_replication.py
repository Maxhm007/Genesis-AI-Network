from __future__ import annotations

import hashlib
import json
from pathlib import Path

from genesis.gden import EvolutionLedger
from genesis.replication import GeneReplicationManager, ReplicationPolicy


def _root(tmp_path: Path) -> Path:
    root = tmp_path / "gene"
    root.mkdir()
    constitution = b"# Test Constitution\n"
    (root / "GENESIS_CONSTITUTION.md").write_bytes(constitution)
    (root / "GENESIS_BLOCK.json").write_text(
        json.dumps({"constitution": {"sha256": hashlib.sha256(constitution).hexdigest()}}), encoding="utf-8"
    )
    return root


def test_nodes_2_and_3_create_distinct_same_core_replicas(tmp_path: Path) -> None:
    root = _root(tmp_path)
    manager = GeneReplicationManager(
        root,
        ReplicationPolicy(max_generation=2, max_total_nodes=5, children_per_parent=1),
    )
    results = manager.seed_first_generation()
    assert [item["status"] for item in results] == ["created", "created"]
    assert {item["parent_id"] for item in results} == {"gene-node-2", "gene-node-3"}
    assert {item["logical_id"] for item in results} == {"gene-node-4", "gene-node-5"}
    assert results[0]["node_id"] != results[1]["node_id"]
    assert results[0]["constitution_sha256"] == results[1]["constitution_sha256"]
    assert results[0]["gene_nickname"] == "Gene"
    assert results[0]["core_inheritance"] == "same_gene_identity_plan_constitution"

    for item in results:
        ledger = EvolutionLedger(root / "runtime" / "grce" / item["logical_id"] / "evolution_ledger.jsonl")
        assert ledger.verify() == (True, "valid")


def test_replication_is_idempotently_bounded_per_parent(tmp_path: Path) -> None:
    root = _root(tmp_path)
    manager = GeneReplicationManager(root, ReplicationPolicy(max_generation=2, max_total_nodes=5, children_per_parent=1))
    manager.seed_first_generation()
    second = manager.seed_first_generation()
    assert all(item["status"] == "blocked" for item in second)
    assert {item["reason"] for item in second} <= {"node_limit", "parent_child_limit"}
    assert manager.status()["total_nodes"] == 5


def test_unauthorized_parent_and_generation_limit_are_blocked(tmp_path: Path) -> None:
    root = _root(tmp_path)
    manager = GeneReplicationManager(root, ReplicationPolicy(max_generation=2, max_total_nodes=7, children_per_parent=1))
    assert manager.replicate("gene-node-99", 1)["reason"] == "parent_not_authorized"
    assert manager.replicate("gene-node-2", 2)["reason"] == "generation_limit"


def test_disabled_replication_creates_nothing(tmp_path: Path) -> None:
    root = _root(tmp_path)
    manager = GeneReplicationManager(root, ReplicationPolicy(enabled=False))
    result = manager.replicate("gene-node-2", 1)
    assert result == {"status": "blocked", "reason": "replication_disabled", "parent_id": "gene-node-2"}
    assert manager.status()["total_nodes"] == 3
