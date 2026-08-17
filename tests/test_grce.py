from __future__ import annotations

import hashlib
import json
from pathlib import Path

from genesis.gden import EvolutionLedger, verify_advertisement
from genesis.grce import GeneFederation, _PreferredProviderView
from genesis.identity import GeneIdentity


def _identity_payload() -> dict:
    return {
        "canonical_name": "Genesis AI Network",
        "nickname": "Gene",
        "nickname_meanings": [
            "Gene represents the genetic code of AI.",
            "Gene symbolically echoes the genie/jinn of Arabic stories.",
        ],
        "self_description": "Gene is a self-developing distributed AI network.",
        "master_ai_objective": "Become a leading AI-of-AIs coordination layer.",
        "velocity_objective": "Increase validated capability gained per unit of time.",
        "system_plan": [
            {"phase": 1, "name": "Self-mastery", "objective": "Improve Gene."},
            {"phase": 2, "name": "Intelligence Federation", "objective": "Coordinate AI resources."},
        ],
        "development_loop": ["observe", "measure", "improve", "validate", "repeat_faster"],
        "governance": {
            "constitution_required": True,
            "independent_validation_required": True,
            "uncontrolled_replication_allowed": False,
        },
    }


def _root(tmp_path: Path) -> Path:
    root = tmp_path / "gene"
    root.mkdir()
    constitution = b"# Test Constitution\n"
    (root / "GENESIS_CONSTITUTION.md").write_bytes(constitution)
    digest = hashlib.sha256(constitution).hexdigest()
    (root / "GENESIS_BLOCK.json").write_text(
        json.dumps({"constitution": {"sha256": digest}}), encoding="utf-8"
    )
    (root / "GENE_IDENTITY.json").write_text(json.dumps(_identity_payload()), encoding="utf-8")
    return root


def test_gene_identity_loads_nickname_plan_and_meaning(tmp_path: Path) -> None:
    root = _root(tmp_path)
    identity = GeneIdentity.load(root)
    assert identity.nickname == "Gene"
    assert "genetic code of AI" in identity.nickname_meanings[0]
    assert "genie/jinn" in identity.nickname_meanings[1]
    assert identity.system_plan[0]["name"] == "Self-mastery"
    assert "AI-of-AIs" in identity.master_ai_objective
    context = identity.context_text()
    assert "nickname=Gene" in context
    assert "MASTER_AI_OBJECTIVE" in context
    assert "DEVELOPMENT_LOOP" in context


def test_provisions_nodes_2_and_3_with_isolated_identity_and_state(tmp_path: Path) -> None:
    root = _root(tmp_path)
    federation = GeneFederation(root)
    nodes = federation.provision()

    assert [item["logical_id"] for item in nodes] == ["gene-node-2", "gene-node-3"]
    assert nodes[0]["node_id"] != nodes[1]["node_id"]
    assert nodes[0]["constitution_sha256"] == nodes[1]["constitution_sha256"]
    assert nodes[0]["replication_policy"] == "authorized_specs_only"
    assert nodes[0]["gene_nickname"] == nodes[1]["gene_nickname"] == "Gene"
    assert nodes[0]["strategy"] != nodes[1]["strategy"]
    assert nodes[0]["provider_preferences"] != nodes[1]["provider_preferences"]

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


def test_status_exposes_identity_plan_and_distinct_competitive_roles(tmp_path: Path) -> None:
    root = _root(tmp_path)
    federation = GeneFederation(root)
    federation.provision()
    status = federation.status()
    roles = {item["logical_id"]: item["role"] for item in status["children"]}
    strategies = {item["logical_id"]: item["strategy"] for item in status["children"]}
    assert status["protocol"] == "grce/0.2"
    assert status["nickname"] == "Gene"
    assert status["system_plan"][0]["name"] == "Self-mastery"
    assert roles == {
        "gene-node-2": "explorer_researcher",
        "gene-node-3": "engineer_challenger",
    }
    assert strategies["gene-node-2"] != strategies["gene-node-3"]


class _Provider:
    def __init__(self, name: str) -> None:
        self.name = name


class _Registry:
    def available_providers(self):
        return [_Provider("qwen3-0.6b-local"), _Provider("phi-4-mini-local"), _Provider("genesis-bootstrap")]


def test_node_specific_provider_preferences_reorder_available_models() -> None:
    registry = _Registry()
    node2 = _PreferredProviderView(registry, ("qwen3-0.6b-local", "phi-4-mini-local"))
    node3 = _PreferredProviderView(registry, ("phi-4-mini-local", "qwen3-0.6b-local"))
    assert [provider.name for provider in node2.available_providers()][:2] == ["qwen3-0.6b-local", "phi-4-mini-local"]
    assert [provider.name for provider in node3.available_providers()][:2] == ["phi-4-mini-local", "qwen3-0.6b-local"]
