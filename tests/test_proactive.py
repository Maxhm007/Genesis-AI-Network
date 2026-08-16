from pathlib import Path

from genesis.proactive import ProactiveDevelopmentLoop


def test_proactive_planner_detects_health_gap(tmp_path: Path):
    (tmp_path / "genesis").mkdir()
    loop = ProactiveDevelopmentLoop(tmp_path)
    plan = loop.plan_next()
    assert plan is not None
    assert "health" in plan.title.lower()
    assert "genesis/health.py" in plan.proposal["files"]


def test_proactive_planner_moves_to_budget_after_health(tmp_path: Path):
    (tmp_path / "genesis").mkdir()
    (tmp_path / "genesis" / "health.py").write_text("# present\n", encoding="utf-8")
    loop = ProactiveDevelopmentLoop(tmp_path)
    plan = loop.plan_next()
    assert plan is not None
    assert "budget" in plan.title.lower()
    assert "genesis/budget.py" in plan.proposal["files"]


def test_proactive_planner_stops_when_bounded_catalog_complete(tmp_path: Path):
    (tmp_path / "genesis").mkdir()
    (tmp_path / "genesis" / "health.py").write_text("# present\n", encoding="utf-8")
    (tmp_path / "genesis" / "budget.py").write_text("# present\n", encoding="utf-8")
    loop = ProactiveDevelopmentLoop(tmp_path)
    assert loop.plan_next() is None
