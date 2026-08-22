from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from genesis.bounded_autonomy_pipeline import BoundedAutonomyPipelineCoordinator
from genesis.improvement import IMPROVEMENT_MODULE_ID, ImprovementModule
from genesis.merge import MERGE_MODULE_ID, MergeModule
from genesis.modules.registry import ModuleRegistry
from genesis.modules.task_queue import GenesisTask


def _task(*, task_type: str, target: str, new_capability: bool = False) -> GenesisTask:
    return GenesisTask(
        task_id="task-test",
        objective="Improve the measured capability.",
        module_id="genesis.coding",
        state="assigned",
        priority=50,
        payload={
            "source": "genesis.evolution_learning",
            "task_type": task_type,
            "target_path": target,
            "capability_key": "software_engineering",
            "baseline_score": 41.0,
            "benchmark_gap": {
                "benchmark_id": "swe_bench_verified",
                "capability_key": "software_engineering",
                "reference_score": 65.0,
            },
            "finding": {"new_capability": new_capability},
        },
        created_at="2026-08-22T00:00:00+00:00",
        updated_at="2026-08-22T00:00:00+00:00",
        max_attempts=4,
    )


def test_canonical_registry_loads_separate_improvement_and_merge_modules() -> None:
    root = Path(__file__).resolve().parents[1]
    registry = ModuleRegistry.from_default_config(root)

    improvement = registry.get(IMPROVEMENT_MODULE_ID)
    merge = registry.get(MERGE_MODULE_ID)
    assert improvement is not None
    assert merge is not None

    assert "code.write_candidate" in improvement.permissions
    assert "candidate.approve" not in improvement.permissions
    assert "validation.bypass" not in improvement.permissions
    assert improvement.metadata["direct_main_write"] is False
    assert improvement.metadata["merge_authority"] is False

    assert merge.protected is True
    assert merge.mutable is False
    assert "code.write_candidate" not in merge.permissions
    assert "candidate.approve" not in merge.permissions
    assert merge.metadata["self_review"] is False
    assert merge.metadata["validation_authority"] is False


def test_improvement_routes_existing_capability_but_not_new_capability() -> None:
    existing = _task(task_type="capability_growth", target="genesis/coding.py")
    new = _task(
        task_type="new_capability",
        target="genesis/learned_capabilities.py",
        new_capability=True,
    )
    record = SimpleNamespace(target_path="genesis/coding.py")
    new_record = SimpleNamespace(target_path="genesis/learned_capabilities.py")

    assert ImprovementModule.is_improvement_task(existing, record) is True
    assert ImprovementModule.is_improvement_task(new, new_record) is False


def test_improvement_objective_has_no_merge_authority() -> None:
    task = _task(task_type="capability_growth", target="genesis/coding.py")
    prepared = ImprovementModule.prepare_task(task, SimpleNamespace(target_path="genesis/coding.py"))

    assert prepared.module_id == IMPROVEMENT_MODULE_ID
    assert "Improve an EXISTING Genesis capability only" in prepared.objective
    assert "do not merge or promote your own candidate" in prepared.objective
    assert "swe_bench_verified" in prepared.objective
    assert prepared.payload["active_submodule"] == IMPROVEMENT_MODULE_ID


def test_merge_requires_review_promotion_and_safe_target(tmp_path, monkeypatch) -> None:
    module = MergeModule(tmp_path)
    monkeypatch.setattr(module, "candidate_present_on_main", lambda _sha: True)
    record = SimpleNamespace(
        task_id="task-merge",
        stage="promoted",
        candidate_sha="abc123",
        target_path="genesis/coding.py",
        history=(
            {"worker": "review", "stage": "validation_ready"},
            {"worker": "promotion", "stage": "promoted"},
        ),
    )

    evidence = module.verify(record)
    assert evidence.approved is True
    assert evidence.reason == "validated_candidate_present_on_main"

    protected = SimpleNamespace(**{**record.__dict__, "target_path": "GENESIS_BLOCK.json"})
    protected_evidence = module.verify(protected)
    assert protected_evidence.approved is False
    assert protected_evidence.reason == "normal_autonomous_merge_target_protected"


def test_bounded_pulse_scheduler_has_improvement_merge_extension_installed() -> None:
    assert BoundedAutonomyPipelineCoordinator._genesis_improvement_merge_installed is True
