from pathlib import Path

from genesis.parallel_engineering import ParallelDevelopmentPlanner


def _planner(tmp_path: Path) -> ParallelDevelopmentPlanner:
    planner = ParallelDevelopmentPlanner(tmp_path)
    planner.velocity_policy = {
        "recent_risk_events": 0,
        "recommended_parallel_candidates": 2,
    }
    planner.velocity_report = {"validated_updates_24h": 8}
    return planner


def test_parallel_planner_selects_two_independent_modules(tmp_path: Path) -> None:
    planner = _planner(tmp_path)
    planner.queue.create("Improve coding reliability", module_id="genesis.coding", priority=90)
    planner.queue.create("Improve application behavior", module_id="genesis.application", priority=80)

    report = planner.plan()

    assert report["capacity"] == 2
    assert len(report["tasks"]) == 2
    assert {row["module_id"] for row in report["tasks"]} == {"genesis.coding", "genesis.application"}


def test_parallel_planner_falls_back_to_one_after_risk(tmp_path: Path) -> None:
    planner = _planner(tmp_path)
    planner.velocity_policy["recent_risk_events"] = 1
    planner.queue.create("Improve coding reliability", module_id="genesis.coding", priority=90)
    planner.queue.create("Improve application behavior", module_id="genesis.application", priority=80)

    report = planner.plan()

    assert report["capacity"] == 1
    assert len(report["tasks"]) == 1


def test_control_plane_task_is_never_paired(tmp_path: Path) -> None:
    planner = _planner(tmp_path)
    planner.queue.create("Repair security boundary", module_id="genesis.security", priority=100)
    planner.queue.create("Improve application behavior", module_id="genesis.application", priority=80)

    report = planner.plan()

    assert len(report["tasks"]) == 1
    assert report["tasks"][0]["module_id"] == "genesis.security"
