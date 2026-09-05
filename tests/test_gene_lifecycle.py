import json
from pathlib import Path

import pytest

from genesis.gene_lifecycle import GeneLifecycleManager, GeneLifecyclePolicy, GeneNeedEvidence


def _registry(path: Path, *, extra_genes=None) -> Path:
    data = {
        "schema_version": 3,
        "registry_authority": "Gene 0",
        "reserved": [{"display_identity": "Gene 001", "serial": 1, "status": "reserved_for_owner_definition"}],
        "genes": [
            {"display_identity": "Gene 0", "serial": 0, "status": "active", "capabilities": ["coordination"]},
            {"display_identity": "Gene 002", "serial": 2, "status": "active", "capabilities": ["research", "validation"]},
            {"display_identity": "Gene 003", "serial": 3, "status": "active", "capabilities": ["engineering", "repair"]},
        ] + list(extra_genes or []),
    }
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def _strong_evidence(**overrides) -> GeneNeedEvidence:
    values = dict(
        backlog_pressure=30,
        capability_gap="benchmark_specialist",
        routing_contention=8,
        resource_capacity=0.8,
        objective="Create a bounded benchmark specialist",
    )
    values.update(overrides)
    return GeneNeedEvidence(**values)


def test_gene0_creates_gene4_and_never_uses_reserved_gene1(tmp_path: Path) -> None:
    registry = _registry(tmp_path / "GENE_REGISTRY.json")
    manager = GeneLifecycleManager(registry, state_path=tmp_path / "state.json")
    result = manager.evaluate_and_create(_strong_evidence(), now=1000)
    assert result["status"] == "candidate_created"
    gene = result["gene"]
    assert gene["serial"] == 4
    assert gene["display_identity"] == "Gene 004"
    assert gene["parent_coordinator"] == "Gene 0"
    assert gene["supporting_genes"] == ["Gene 002", "Gene 003"]
    assert gene["model_profile"]["identity_binding"] is False
    assert gene["model_profile"]["replaceable"] is True
    assert gene["status"] == "candidate"


def test_same_need_is_idempotent_and_existing_gene_is_preferred(tmp_path: Path) -> None:
    registry = _registry(tmp_path / "GENE_REGISTRY.json")
    manager = GeneLifecycleManager(registry, state_path=tmp_path / "state.json")
    evidence = _strong_evidence()
    first = manager.evaluate_and_create(evidence, now=1000)
    second = manager.evaluate_and_create(evidence, now=1001)
    assert first["created"] is True
    assert second["created"] is False
    assert second["status"] == "existing_gene_reused"

    covered_registry = _registry(
        tmp_path / "covered.json",
        extra_genes=[{"display_identity": "Gene 004", "serial": 4, "status": "active", "capabilities": ["benchmark_specialist"]}],
    )
    covered = GeneLifecycleManager(covered_registry, state_path=tmp_path / "covered-state.json")
    absorbed = covered.evaluate_and_create(evidence, now=1000)
    assert absorbed["status"] == "absorbed_by_existing_gene"
    assert absorbed["created"] is False


def test_insufficient_evidence_and_resource_pressure_do_not_spawn(tmp_path: Path) -> None:
    registry = _registry(tmp_path / "GENE_REGISTRY.json")
    manager = GeneLifecycleManager(registry, state_path=tmp_path / "state.json")
    weak = manager.evaluate_and_create(GeneNeedEvidence(capability_gap="one_gap"), now=1000)
    assert weak["status"] == "insufficient_evidence"
    blocked = manager.evaluate_and_create(_strong_evidence(resource_capacity=0.1), now=1000)
    assert blocked["status"] == "resource_blocked"
    data = json.loads(registry.read_text(encoding="utf-8"))
    assert [gene["serial"] for gene in data["genes"]] == [0, 2, 3]


def test_memory_pressure_creates_replicated_memory_shard_descriptor(tmp_path: Path) -> None:
    registry = _registry(tmp_path / "GENE_REGISTRY.json")
    manager = GeneLifecycleManager(registry, state_path=tmp_path / "state.json")
    evidence = GeneNeedEvidence(
        backlog_pressure=30,
        memory_pressure=0.95,
        memory_domain="materials science",
        routing_contention=8,
        resource_capacity=0.9,
        objective="Shard materials knowledge",
    )
    result = manager.evaluate_and_create(evidence, now=1000)
    memory = result["gene"]["memory_responsibility"]
    assert memory["mode"] == "shard"
    assert memory["domain"] == "materials science"
    assert memory["replicas"] == ["Gene 0"]
    assert memory["critical_identity_single_owner_forbidden"] is True


def test_gene2_and_gene3_are_advisory_and_cannot_mutate_registry(tmp_path: Path) -> None:
    registry = _registry(tmp_path / "GENE_REGISTRY.json")
    manager = GeneLifecycleManager(registry, state_path=tmp_path / "state.json")
    advice = manager.advisory("Gene 002", "create benchmark specialist", {"backlog": 30})
    assert advice["registry_mutation"] is False
    before = registry.read_text(encoding="utf-8")
    with pytest.raises(PermissionError):
        manager.evaluate_and_create(_strong_evidence(), authority="Gene 002", now=1000)
    assert registry.read_text(encoding="utf-8") == before


def test_lifecycle_transitions_are_bounded_and_recorded(tmp_path: Path) -> None:
    registry = _registry(tmp_path / "GENE_REGISTRY.json")
    manager = GeneLifecycleManager(registry, state_path=tmp_path / "state.json")
    created = manager.evaluate_and_create(_strong_evidence(), now=1000)
    serial = created["gene"]["serial"]
    assert manager.transition(serial, "active", reason="descriptor validated", now=1010)["gene"]["status"] == "active"
    assert manager.transition(serial, "degraded", reason="health threshold", now=1020)["gene"]["status"] == "degraded"
    assert manager.transition(serial, "suspended", reason="resource pressure", now=1030)["gene"]["status"] == "suspended"
    assert manager.transition(serial, "retiring", reason="duplicate responsibility", now=1040)["gene"]["status"] == "retiring"
    retired = manager.transition(serial, "retired", reason="responsibility migrated", now=1050)["gene"]
    assert retired["status"] == "retired"
    assert len(retired["lifecycle_events"]) == 5
    with pytest.raises(ValueError):
        manager.transition(serial, "active", reason="cannot revive retired", now=1060)


def test_hard_limit_prevents_runaway_creation(tmp_path: Path) -> None:
    extra = [
        {"display_identity": f"Gene {serial:03d}", "serial": serial, "status": "active", "capabilities": [f"cap_{serial}"]}
        for serial in range(4, 8)
    ]
    registry = _registry(tmp_path / "GENE_REGISTRY.json", extra_genes=extra)
    policy = GeneLifecyclePolicy(active_gene_hard_limit=7)
    manager = GeneLifecycleManager(registry, state_path=tmp_path / "state.json", policy=policy)
    result = manager.evaluate_and_create(_strong_evidence(capability_gap="new_gap"), now=1000)
    assert result["status"] == "hard_limit_reached"
    assert result["created"] is False

def test_core_processor_exposes_gene0_lifecycle_authority(tmp_path: Path) -> None:
    from genesis.core_processor import GenesisCoreProcessor

    _registry(tmp_path / "GENE_REGISTRY.json")
    core = GenesisCoreProcessor(tmp_path)
    result = core.evaluate_gene_lifecycle(_strong_evidence(), now=1000)
    assert result["status"] == "candidate_created"
    assert result["gene"]["serial"] == 4
    assert (tmp_path / "runtime" / "gene_lifecycle_state.json").is_file()

