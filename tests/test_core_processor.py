from __future__ import annotations

from pathlib import Path

from genesis.core_processor import GenesisCoreProcessor
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
    assert (tmp_path / "runtime" / "core_processor.json").is_file()


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
