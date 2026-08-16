from pathlib import Path

import pytest

from genesis.modules.manager import ModuleManager
from genesis.modules.registry import ModuleRegistry
from genesis.modules.types import ModuleManifest, ModuleProposal


def test_default_registry_loads_existing_genesis_modules():
    root = Path(__file__).resolve().parents[1]
    registry = ModuleRegistry.from_default_config(root)
    ids = {module.module_id for module in registry.all()}
    assert "genesis.communication" in ids
    assert "genesis.repair" in ids
    assert "genesis.self_development" in ids
    assert "genesis.validation" in ids
    assert registry.get("genesis.identity").protected is True


def test_default_registry_loads_resource_intelligence_extensions():
    root = Path(__file__).resolve().parents[1]
    registry = ModuleRegistry.from_default_config(root)
    ids = {module.module_id for module in registry.all()}
    assert {"genesis.router", "genesis.efficiency", "genesis.scorecard"}.issubset(ids)
    assert "capability_per_compute" in registry.get("genesis.efficiency").capabilities


def test_capability_gap_can_propose_reasoning_module_once():
    registry = ModuleRegistry()
    manager = ModuleManager(registry)
    gap = {"capability": "advanced_reasoning", "score": 4, "max_score": 15}
    proposal = manager.propose_for_capability_gap(gap)
    assert proposal is not None
    assert proposal.action == "add"
    assert proposal.target_module_id == "genesis.reasoning"
    assert proposal.status == "candidate"

    registry.register(ModuleManifest(**{**proposal.candidate_manifest, "status": "active"}))
    assert manager.propose_for_capability_gap(gap) is None


def test_unvalidated_module_cannot_activate():
    registry = ModuleRegistry()
    manager = ModuleManager(registry)
    proposal = manager.propose_for_capability_gap(
        {"capability": "advanced_reasoning", "score": 4, "max_score": 15}
    )
    assert proposal is not None
    with pytest.raises(ValueError, match="independently validated"):
        manager.activate_validated(proposal)


def test_protected_validation_module_cannot_be_retired():
    root = Path(__file__).resolve().parents[1]
    registry = ModuleRegistry.from_default_config(root)
    manager = ModuleManager(registry)
    proposal = ModuleProposal(
        proposal_id="test",
        action="retire",
        target_module_id="genesis.validation",
        title="bad proposal",
        rationale="test",
        requested_by="test",
    )
    with pytest.raises(ValueError, match="protected"):
        manager.validate_proposal(proposal)
