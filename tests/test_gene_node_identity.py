from __future__ import annotations

import hashlib
import json
from pathlib import Path

from genesis.node import GenesisNode
from genesis.providers import ProviderRegistry


def _root(tmp_path: Path) -> Path:
    root = tmp_path / "gene"
    root.mkdir()
    constitution = b"# Test Constitution\n"
    (root / "GENESIS_CONSTITUTION.md").write_bytes(constitution)
    digest = hashlib.sha256(constitution).hexdigest()
    (root / "GENESIS_BLOCK.json").write_text(json.dumps({"constitution": {"sha256": digest}}), encoding="utf-8")
    (root / "GENE_IDENTITY.json").write_text(
        json.dumps({
            "canonical_name": "Genesis AI Network",
            "nickname": "Gene",
            "nickname_meanings": ["genetic code of AI", "genie/jinn symbolism"],
            "self_description": "self-developing distributed AI network",
            "master_ai_objective": "AI-of-AIs coordination",
            "velocity_objective": "validated capability per unit of time",
            "system_plan": [{"phase": 1, "name": "Self-mastery", "objective": "improve"}],
            "development_loop": ["observe", "validate", "repeat_faster"],
            "governance": {"constitution_required": True},
        }),
        encoding="utf-8",
    )
    return root


def test_core_node_status_knows_gene_nickname_and_plan(tmp_path: Path) -> None:
    root = _root(tmp_path)
    node = GenesisNode(root, db_path=root / "state" / "test.db", providers=ProviderRegistry(include_bootstrap=True))
    try:
        payload = node.status_payload()
        assert payload["nickname"] == "Gene"
        assert payload["network"] == "Genesis AI Network"
        assert payload["master_ai_objective"] == "AI-of-AIs coordination"
        assert payload["system_plan"][0]["name"] == "Self-mastery"
    finally:
        node.conn.close()
