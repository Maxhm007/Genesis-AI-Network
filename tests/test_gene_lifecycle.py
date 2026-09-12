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
