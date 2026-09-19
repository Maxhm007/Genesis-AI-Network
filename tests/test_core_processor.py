from __future__ import annotations

from pathlib import Path

from genesis.core_processor import GenesisCoreProcessor
from genesis.gene_lifecycle import GeneNeed
from genesis.resource import ResourceModule


def test_core_processor_routes_normal_task_and_publishes_state(tmp_path: Path) -> None:
    processor = GenesisCoreProcessor(tmp_path)
    task = processor.queue.create(
        "Fix a bounded coding defect",
        module_id="genesis.coding",
        priority=80,
        payload={"target_path": "genesis/example.py"},
    )

    result = processor.cycle()

    assert result["processor"] == "genesis.core_processor"
    assert result["authority"]["intelligence_provider"] is False
    assert result["authority"]["direct_code_promotion"] is False
    assert result["routing"]["status"] == "assigned"
    assert result["dispatch"]["task_id"] == task.task_id
    assert result["dispatch"]["module_id"] == "genesis.coding"
    assert result["dispatch"]["lane"] == "normal"
    assert result["dispatch"]["target_gene_id"] == "gene-node-3"
    assert result["dispatch"]["model"] == "deepseek-ai/DeepSeek-R1-Distill-Qwen-1.5B"
    assert result["coordinator"]["logical_id"] == "gene-node-1"
    assert (tmp_path / "runtime" / "core_processor.json").is_file()


def test_core_processor_routes_research_to_gene_2(tmp_path: Path) -> None:
    processor = GenesisCoreProcessor(tmp_path)
    processor.queue.create(
        "Research current evidence for a bounded hypothesis",
        module_id="genesis.research",
        priority=70,
    )

    result = processor.cycle()

    assert result["dispatch"]["target_gene_id"] == "gene-node-2"
    assert result["dispatch"]["model"] == "Qwen/Qwen3-1.7B"
    assert result["dispatch"]["model_license"] == "Apache-2.0"


def test_core_processor_marks_protected_target_privileged(tmp_path: Path) -> None:
    processor = GenesisCoreProcessor(tmp_path)
    processor.queue.create(
        "Review a workflow security change",
        module_id="genesis.coding",
        priority=90,
        payload={"target_path": ".github/workflows/proactive-development.yml"},
    )

    result = processor.cycle()

    assert result["routing"]["status"] == "assigned"
    assert result["dispatch"]["lane"] == "privileged"


def test_core_processor_throttles_dispatch_when_capacity_is_low(tmp_path: Path) -> None:
    processor = GenesisCoreProcessor(tmp_path)
    task = processor.queue.create("Run later", module_id="genesis.research", priority=50)
    snapshot = ResourceModule().snapshot(95, 95, 95, battery_percent=10, network_available=True)

    result = processor.cycle(snapshot)

    assert result["resource"]["mode"] == "throttled"
    assert result["resource"]["dispatch_allowed"] is False
    assert result["routing"]["status"] == "resource_throttled"
    assert processor.queue.get(task.task_id).state == "new"


def test_core_processor_can_run_bounded_gene_lifecycle_evaluation(tmp_path: Path) -> None:
    registry = {
        "schema_version": 3,
        "registry_authority": "Gene 0",
        "reserved": [{"display_identity": "Gene 001", "serial": 1, "status": "reserved_for_owner_definition"}],
        "genes": [
            {"display_identity": "Gene 0", "serial": 0, "logical_id": "gene-node-1", "role": "coordinator", "status": "active", "capabilities": ["coordination"]},
            {"display_identity": "Gene 002", "serial": 2, "logical_id": "gene-node-2", "role": "research", "status": "active", "capabilities": ["research", "validation"]},
            {"display_identity": "Gene 003", "serial": 3, "logical_id": "gene-node-3", "role": "engineering", "status": "active", "capabilities": ["engineering", "repair"]},
        ],
    }
    (tmp_path / "GENE_REGISTRY.json").write_text(__import__("json").dumps(registry), encoding="utf-8")
    processor = GenesisCoreProcessor(tmp_path)
    need = GeneNeed(
        role="memory_shard_specialist",
        objective="Relieve memory pressure",
        capabilities=("memory_sharding", "knowledge_routing"),
        evidence={"memory_pressure": True, "backlog_pressure": True},
        memory_responsibility="longevity-shard",
        replicas=("Gene 0",),
    )

    result = processor.cycle(gene_needs=(need,))

    assert result["gene_lifecycle"]["status"] == "evaluated"
    assert result["gene_lifecycle"]["authority"] == "Gene 0"
    assert result["gene_lifecycle"]["decisions"][0]["action"] == "created_candidate"
    persisted = __import__("json").loads((tmp_path / "GENE_REGISTRY.json").read_text())
    assert any(gene["serial"] == 4 for gene in persisted["genes"])



def test_core_processor_recalls_only_validated_persistent_memory(tmp_path: Path) -> None:
    processor = GenesisCoreProcessor(tmp_path)
    trusted = processor.memory.store.add(
        memory_type="repair",
        topic="bounded coding defect",
        content="Use validated repair knowledge before repeating a failed coding strategy.",
        source_type="verified_issue",
        source_ref="#829",
        state="candidate",
    )
    processor.memory.store.transition(
        trusted.memory_id,
        "validated",
        evidence={"full_suite_passed": True},
    )
    processor.memory.store.add(
        memory_type="repair",
        topic="bounded coding defect",
        content="Unverified guess that must not enter normal recall.",
        source_type="draft",
        source_ref="draft-1",
        state="candidate",
    )
    processor.queue.create(
        "Fix a bounded coding defect with prior repair knowledge",
        module_id="genesis.coding",
        priority=80,
        payload={"target_path": "genesis/example.py"},
    )

    result = processor.cycle()

    recalled = result["memory"]["recalled"]
    assert result["memory"]["policy"].startswith("validated-only")
    assert len(recalled) == 1
    assert recalled[0]["memory_id"] == trusted.memory_id
    assert "Unverified guess" not in str(recalled)
