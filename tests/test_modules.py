from pathlib import Path

import pytest

from genesis.modules.manager import ModuleManager
from genesis.modules.registry import ModuleRegistry
from genesis.modules.runtime import ModularGenesis
from genesis.modules.types import ModuleProposal


def test_default_registry_loads_existing_genesis_modules():
    root = Path(__file__).resolve().parents[1]
    registry = ModuleRegistry.from_default_config(root)
    ids = {module.module_id for module in registry.all()}
    assert "genesis.communication" in ids
    assert "genesis.repair" in ids
    assert "genesis.self_development" in ids
    assert "genesis.validation" in ids
    assert registry.get("genesis.identity").protected is True


def test_capability_gap_can_propose_reasoning_module():
    root = Path(__file__).resolve().parents[1]
    modular = ModularGenesis(root)
    status = modular.status()
    proposals = status["module_change_proposals"]
    assert any(item["capability"] == "advanced_reasoning" for item in proposals)
    assert all(item["status"] == "candidate" for item in proposals)


def test_unvalidated_module_cannot_activate():
    root = Path(__file__).resolve().parents[1]
    registry = ModuleRegistry.from_default_config(root)
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
