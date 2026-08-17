from __future__ import annotations

import hashlib
import json
from pathlib import Path

from genesis.independent_evolution import EvolutionProfile, IndependentGeneEvolution
from genesis.peer_network import GenePeerNetwork
from genesis.providers import ProviderRegistry


class FakeProvider:
    name = "fake"

    def available(self) -> bool:
        return True

    def generate(self, prompt: str, **kwargs):
        return {"text": "independent result"}


def _root(tmp_path: Path) -> Path:
    root = tmp_path / "gene"
    root.mkdir()
    constitution = b"# Test Constitution\n"
    (root / "GENESIS_CONSTITUTION.md").write_bytes(constitution)
    (root / "GENESIS_BLOCK.json").write_text(
        json.dumps({"constitution": {"sha256": hashlib.sha256(constitution).hexdigest()}}), encoding="utf-8"
    )
    return root


def _registry() -> ProviderRegistry:
    registry = ProviderRegistry(include_bootstrap=False)
    registry.register(FakeProvider())
    return registry


def test_gene_nodes_keep_separate_development_journals(tmp_path: Path) -> None:
    root = _root(tmp_path)
    node2 = IndependentGeneEvolution(root, EvolutionProfile("gene-node-2", "research", "breadth", "improve"), _registry())
    node3 = IndependentGeneEvolution(root, EvolutionProfile("gene-node-3", "engineering", "skeptical", "improve"), _registry())
    record2 = node2.run_cycle()
    record3 = node3.run_cycle()
    assert record2["logical_id"] == "gene-node-2"
    assert record3["logical_id"] == "gene-node-3"
    assert record2["node_id"] != record3["node_id"]
    assert (root / "runtime/grce/gene-node-2/independent_evolution.jsonl").exists()
    assert (root / "runtime/grce/gene-node-3/independent_evolution.jsonl").exists()


def test_shared_knowledge_is_considered_but_not_auto_adopted(tmp_path: Path) -> None:
    root = _root(tmp_path)
    network = GenePeerNetwork(root)
    packet = network.publish_knowledge("gene-node-2", "gene-development", "candidate idea", {"score": 1}, {"source": "node2"})
    node3 = IndependentGeneEvolution(root, EvolutionProfile("gene-node-3", "engineering", "skeptical", "improve"), _registry())
    record = node3.run_cycle()
    assert packet["packet_id"] in record["peer_packets_considered"]
    decisions = root / "runtime/grce/gene-node-3/knowledge_decisions.jsonl"
    assert not decisions.exists(), "peer knowledge must not be auto-adopted"
