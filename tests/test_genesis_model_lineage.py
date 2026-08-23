from __future__ import annotations

import json
from pathlib import Path


def _root() -> Path:
    return Path(__file__).resolve().parents[1]


def test_qwen_is_foundation_ancestor_not_genesis_owned_weights() -> None:
    root = _root()
    lineage = json.loads((root / "config" / "genesis_model_lineage.json").read_text(encoding="utf-8"))
    foundation = lineage["active_foundation"]

    assert foundation["family"] == "Qwen"
    assert foundation["model_id"] == "Qwen/Qwen3-0.6B"
    assert foundation["runtime_provider_name"] == "qwen3-0.6b-genesis-core"
    assert foundation["relationship"] == "initial_foundation_ancestor"
    assert foundation["genesis_owned_weights"] is False
    assert "new weights or adapters" in lineage["naming_rule"]


def test_cognition_and_independent_authority_are_separate() -> None:
    root = _root()
    lineage = json.loads((root / "config" / "genesis_model_lineage.json").read_text(encoding="utf-8"))
    cognitive = set(lineage["cognitive_roles"])
    authority = set(lineage["independent_authority"])

    assert {"planning", "research", "learning", "coding", "repair", "internal_review", "communication"} <= cognitive
    assert {"repository_test_suite", "security_gate", "validator_a", "validator_b", "signed_quorum", "external_benchmark_graders"} <= authority
    assert cognitive.isdisjoint(authority)


def test_gene_pulse_runs_declared_qwen_foundation() -> None:
    root = _root()
    lineage = json.loads((root / "config" / "genesis_model_lineage.json").read_text(encoding="utf-8"))
    pulse = (root / ".github" / "workflows" / "gene-pulse.yml").read_text(encoding="utf-8")
    foundation = lineage["active_foundation"]

    assert f"GENESIS_PROVIDER_NAME: {foundation['runtime_provider_name']}" in pulse
    assert f"--model {foundation['model_id']}" in pulse
