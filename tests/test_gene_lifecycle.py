import json
from pathlib import Path

from genesis.gene_lifecycle import GeneLifecycleConfig, GeneLifecycleManager, GeneNeed


def _registry(tmp_path: Path) -> Path:
    path = tmp_path / "GENE_REGISTRY.json"
    path.write_text(json.dumps({
        "schema_version": 3,
        "registry_authority": "Gene 0",
        "reserved": [{"display_identity": "Gene 001", "serial": 1, "status": "reserved_for_owner_definition"}],
        "genes": [
            {"display_identity": "Gene 0", "serial": 0, "logical_id": "gene-node-1", "role": "coordinator", "status": "active", "capabilities": ["coordination"]},
            {"display_identity": "Gene 002", "serial": 2, "logical_id": "gene-node-2", "role": "research", "status": "active", "capabilities": ["research", "validation"]},
            {"display_identity": "Gene 003", "serial": 3, "logical_id": "gene-node-3", "role": "engineering", "status": "active", "capabilities": ["engineering", "repair"]},
        ],
    }), encoding="utf-8")
    return path


def _need(**evidence) -> GeneNeed:
    return GeneNeed(
        role="memory_shard_specialist",
        objective="Relieve sustained memory/library pressure",
        capabilities=("memory_sharding", "knowledge_routing"),
        memory_responsibility="longevity-library-shard-a",
        replicas=("Gene 0",),
        evidence=evidence,
    )


def test_insufficient_evidence_creates_nothing(tmp_path: Path):
    manager = GeneLifecycleManager(_registry(tmp_path))
    result = manager.create_candidate(_need(memory_pressure=True))
    assert result["action"] == "none"
    assert result["reason"] == "insufficient_evidence"


def test_existing_gene_is_preferred(tmp_path: Path):
    path = _registry(tmp_path)
    data = json.loads(path.read_text())
    data["genes"][1]["capabilities"].extend(["memory_sharding", "knowledge_routing"])
    path.write_text(json.dumps(data), encoding="utf-8")
    manager = GeneLifecycleManager(path)
    result = manager.create_candidate(_need(memory_pressure=True, backlog_pressure=True))
    assert result["action"] == "none"
    assert result["reason"] == "existing_gene_can_absorb"


def test_gene0_creates_gene4_and_never_gene1(tmp_path: Path):
    path = _registry(tmp_path)
    manager = GeneLifecycleManager(path)
    result = manager.create_candidate(_need(memory_pressure=True, backlog_pressure=True))
    assert result["action"] == "created_candidate"
    gene = result["gene"]
    assert gene["serial"] == 4
    assert gene["display_identity"] == "Gene 004"
    assert gene["parent_coordinator"] == "Gene 0"
    assert gene["supporting_genes"] == ["Gene 002", "Gene 003"]
    assert gene["model_policy"] == "replaceable_compute_not_identity"
    assert gene["memory_responsibility"] == "longevity-library-shard-a"
    assert gene["status"] == "candidate"
    persisted = json.loads(path.read_text())
    assert any(row["serial"] == 4 for row in persisted["genes"])
    assert not any(row["serial"] == 1 for row in persisted["genes"])


def test_same_need_is_idempotent(tmp_path: Path):
    path = _registry(tmp_path)
    manager = GeneLifecycleManager(path)
    first = manager.create_candidate(_need(memory_pressure=True, backlog_pressure=True))
    second = manager.create_candidate(_need(memory_pressure=True, backlog_pressure=True))
    assert first["action"] == "created_candidate"
    assert second["action"] == "none"
    assert second["reason"] == "duplicate_need"
    persisted = json.loads(path.read_text())
    assert [row["serial"] for row in persisted["genes"]].count(4) == 1


def test_candidate_validates_then_activates_and_transitions(tmp_path: Path):
    path = _registry(tmp_path)
    manager = GeneLifecycleManager(path)
    manager.create_candidate(_need(memory_pressure=True, backlog_pressure=True))
    active = manager.activate_if_valid(4)
    assert active["gene"]["status"] == "active"
    degraded = manager.transition(4, "degraded", "health check below target")
    assert degraded["gene"]["status"] == "degraded"
    suspended = manager.transition(4, "suspended", "resource budget exceeded")
    assert suspended["gene"]["status"] == "suspended"
    retiring = manager.transition(4, "retiring", "responsibility merged into another Gene")
    retired = manager.transition(4, "retired", "retirement complete")
    assert retiring["gene"]["status"] == "retiring"
    assert retired["gene"]["status"] == "retired"


def test_hard_limit_prevents_runaway_creation(tmp_path: Path):
    path = _registry(tmp_path)
    manager = GeneLifecycleManager(path, GeneLifecycleConfig(hard_active_limit=3))
    result = manager.create_candidate(_need(memory_pressure=True, backlog_pressure=True))
    assert result["action"] == "none"
    assert result["reason"] == "hard_active_gene_limit"


def test_soft_limit_prevents_additional_candidate(tmp_path: Path):
    path = _registry(tmp_path)
    manager = GeneLifecycleManager(path, GeneLifecycleConfig(soft_active_limit=3, hard_active_limit=10))
    result = manager.create_candidate(_need(memory_pressure=True, backlog_pressure=True))
    assert result["action"] == "none"
    assert result["reason"] == "soft_active_gene_limit"


def test_cycle_spawn_limit_bounds_multiple_needs(tmp_path: Path):
    path = _registry(tmp_path)
    manager = GeneLifecycleManager(
        path,
        GeneLifecycleConfig(max_new_genes_per_cycle=1, cooldown_seconds=0),
    )
    first = _need(memory_pressure=True, backlog_pressure=True)
    second = GeneNeed(
        role="validator_redundancy",
        objective="Add independent validation redundancy",
        capabilities=("independent_validation",),
        evidence={"reliability_need": True, "independent_validation_need": True},
    )

    results = manager.evaluate_cycle([first, second])

    assert results[0]["action"] == "created_candidate"
    assert results[1]["action"] == "none"
    assert results[1]["reason"] == "cycle_spawn_limit"


def test_retired_need_obeys_cooldown_before_recreation(tmp_path: Path, monkeypatch):
    path = _registry(tmp_path)
    manager = GeneLifecycleManager(path, GeneLifecycleConfig(cooldown_seconds=3600))
    now = manager._now()
    monkeypatch.setattr(manager, "_now", lambda: now)
    manager.create_candidate(_need(memory_pressure=True, backlog_pressure=True))
    manager.transition(4, "retired", "candidate rejected after evaluation")

    result = manager.create_candidate(_need(memory_pressure=True, backlog_pressure=True))

    assert result["action"] == "none"
    assert result["reason"] == "cooldown_active"
    assert result["cooldown_remaining"] > 0


def test_activation_respects_total_parallel_task_budget(tmp_path: Path):
    path = _registry(tmp_path)
    data = json.loads(path.read_text())
    data["genes"][1]["resource_limits"] = {"max_parallel_tasks": 2}
    data["genes"][2]["resource_limits"] = {"max_parallel_tasks": 2}
    data["genes"][0]["resource_limits"] = {"max_parallel_tasks": 2}
    path.write_text(json.dumps(data), encoding="utf-8")

    manager = GeneLifecycleManager(
        path,
        GeneLifecycleConfig(max_total_parallel_tasks=6),
    )
    manager.create_candidate(_need(memory_pressure=True, backlog_pressure=True))
    result = manager.activate_if_valid(4)

    assert result["action"] == "none"
    assert result["reason"] == "resource_budget_exceeded"


def test_critical_memory_requires_core_replica_before_activation(tmp_path: Path):
    path = _registry(tmp_path)
    manager = GeneLifecycleManager(path)
    need = GeneNeed(
        role="identity_memory_shard",
        objective="Shard critical identity memory",
        capabilities=("memory_sharding",),
        evidence={"memory_pressure": True, "reliability_need": True},
        memory_responsibility="identity-governance-shard",
        replicas=("Gene 009",),
    )
    manager.create_candidate(need)

    result = manager.activate_if_valid(4)

    assert result["action"] == "none"
    assert result["reason"] == "critical_memory_requires_core_replica"


def test_merge_responsibilities_moves_source_to_retiring(tmp_path: Path):
    path = _registry(tmp_path)
    manager = GeneLifecycleManager(path)
    manager.create_candidate(_need(memory_pressure=True, backlog_pressure=True))
    manager.activate_if_valid(4)

    data = json.loads(path.read_text())
    data["genes"].append({
        "display_identity": "Gene 005",
        "serial": 5,
        "logical_id": "gene-node-5",
        "role": "replacement_memory_gene",
        "objective": "Receive merged responsibility",
        "status": "active",
        "capabilities": ["knowledge_routing"],
        "model_policy": "replaceable_compute_not_identity",
        "resource_limits": {"max_parallel_tasks": 1},
        "success_metrics": ["health_status"],
        "memory_responsibility": "general-memory",
        "memory_replicas": ["Gene 0"],
    })
    path.write_text(json.dumps(data), encoding="utf-8")

    result = manager.merge_responsibilities(4, 5, "duplicate responsibility detected")

    assert result["action"] == "responsibilities_merged"
    assert result["source"]["status"] == "retiring"
    assert "memory_sharding" in result["target"]["capabilities"]
    assert "longevity-library-shard-a" in result["target"]["memory_responsibilities"]


def test_memory_query_routes_to_shard_then_falls_back_to_gene0(tmp_path: Path):
    path = _registry(tmp_path)
    manager = GeneLifecycleManager(path)
    manager.create_candidate(_need(memory_pressure=True, backlog_pressure=True))
    manager.activate_if_valid(4)

    routed = manager.route_memory_query("longevity-library-shard-a")
    fallback = manager.route_memory_query("unknown-domain")

    assert [gene["serial"] for gene in routed] == [4]
    assert [gene["serial"] for gene in fallback] == [0]


def test_lifecycle_decisions_are_recorded(tmp_path: Path):
    path = _registry(tmp_path)
    manager = GeneLifecycleManager(path)
    manager.create_candidate(_need(memory_pressure=True))

    data = json.loads(path.read_text())

    assert data["lifecycle_decisions"]
    assert data["lifecycle_decisions"][-1]["authority"] == "Gene 0"
    assert data["lifecycle_decisions"][-1]["reason"] == "insufficient_evidence"
