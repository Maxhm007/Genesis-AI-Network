from pathlib import Path

import pytest

from genesis.modules.manager import ModuleManager
from genesis.modules.registry import ModuleRegistry
from genesis.modules.types import ModuleProposal


def test_default_registry_loads_consolidated_genesis_architecture():
    root = Path(__file__).resolve().parents[1]
    registry = ModuleRegistry.from_default_config(root)
    ids = {module.module_id for module in registry.all()}
    assert len(ids) == 25
    assert {
        "genesis.identity",
        "genesis.automation",
        "genesis.task_manager",
        "genesis.ai_team",
        "genesis.research",
        "genesis.knowledge_evidence",
        "genesis.memory",
        "genesis.intelligence_provider",
        "genesis.model_scout",
        "genesis.router",
        "genesis.engineering",
        "genesis.self_development",
        "genesis.security",
        "genesis.validation",
        "genesis.update_version",
        "genesis.evaluation_lab",
        "genesis.capability_scorecard",
        "genesis.resource_efficiency",
        "genesis.gden_network",
        "genesis.blockchain",
        "genesis.peer_compute",
        "genesis.application",
        "genesis.communication",
        "genesis.devlab",
        "genesis.autonomy_pipeline",
    } == ids
    assert registry.get("genesis.identity").protected is True
    assert registry.get("genesis.validation").protected is True


def test_legacy_module_ids_resolve_to_canonical_modules():
    root = Path(__file__).resolve().parents[1]
    registry = ModuleRegistry.from_default_config(root)
    assert registry.get("genesis.task_queue").module_id == "genesis.task_manager"
    assert registry.get("genesis.task_router").module_id == "genesis.task_manager"
    assert registry.get("genesis.coding").module_id == "genesis.engineering"
    assert registry.get("genesis.repair").module_id == "genesis.engineering"
    assert registry.get("genesis.provider").module_id == "genesis.intelligence_provider"
    assert registry.get("genesis.reasoning").module_id == "genesis.intelligence_provider"
    assert registry.get("genesis.ai_score").module_id == "genesis.capability_scorecard"
    assert registry.get("genesis.scorecard").module_id == "genesis.capability_scorecard"
    assert registry.get("genesis.efficiency").module_id == "genesis.resource_efficiency"
    assert registry.get("genesis.gden").module_id == "genesis.gden_network"
    assert registry.get("genesis.network").module_id == "genesis.gden_network"
    assert registry.get("genesis.updater").module_id == "genesis.update_version"
    assert registry.get("genesis.versioning").module_id == "genesis.update_version"


def test_capability_owners_are_canonical_modules():
    root = Path(__file__).resolve().parents[1]
    registry = ModuleRegistry.from_default_config(root)
    assert registry.capability_owners("capability_per_compute") == ["genesis.resource_efficiency"]
    assert "genesis.engineering" in registry.capability_owners("debugging")
    assert registry.capability_owners("development_workspace") == ["genesis.devlab"]


def test_existing_reasoning_provider_prevents_duplicate_reasoning_module():
    root = Path(__file__).resolve().parents[1]
    registry = ModuleRegistry.from_default_config(root)
    manager = ModuleManager(registry)
    gap = {"capability": "advanced_reasoning", "score": 4, "max_score": 15}
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
