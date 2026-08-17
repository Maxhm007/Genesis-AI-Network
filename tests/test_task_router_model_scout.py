from __future__ import annotations

from pathlib import Path

from genesis.model_scout import ModelCandidate, ModelScoutModule
from genesis.modules.task_queue import PersistentTaskQueue
from genesis.task_router import TaskRouterModule


def test_task_router_assigns_highest_priority_and_keeps_todo(tmp_path: Path):
    queue = PersistentTaskQueue(tmp_path / "runtime" / "genesis_tasks.sqlite3")
    low = queue.create("Research a longevity paper", priority=40)
    high = queue.create("Fix critical security authentication issue", priority=95)

    router = TaskRouterModule(tmp_path)
    result = router.assign_next()

    assert result["status"] == "assigned"
    assert result["task"]["task_id"] == high.task_id
    assert result["decision"]["module_id"] == "genesis.security"
    assert queue.get(low.task_id).state == "new"
    assert queue.get(high.task_id).state == "assigned"
    todo = router.write_todo()
    assert todo["pending"] == 2


def test_task_router_uses_ai_team_only_for_complex_cross_module_work(tmp_path: Path):
    queue = PersistentTaskQueue(tmp_path / "runtime" / "genesis_tasks.sqlite3")
    task = queue.create(
        "Review architecture and security tradeoff for distributed blockchain update",
        priority=90,
        payload={"cross_module": True},
    )
    decision = TaskRouterModule.route(task)
    assert decision.use_ai_team is True


def test_model_scout_recommends_validation_before_activation():
    scout = ModelScoutModule()
    discovered = ModelCandidate(
        "candidate-small",
        "https://example.test/small",
        "apache-2.0",
        state="discovered",
        resource_cost=2.0,
        capabilities=("reasoning",),
    )
    validated = ModelCandidate(
        "candidate-validated",
        "https://example.test/validated",
        "apache-2.0",
        state="validated",
        benchmark_score=80.0,
        resource_cost=4.0,
        capabilities=("reasoning",),
    )

    recommendations = scout.recommend([discovered, validated], capability="reasoning")
    by_name = {item.name: item for item in recommendations}
    assert by_name["candidate-small"].recommendation == "evaluate_next"
    assert by_name["candidate-validated"].recommendation == "candidate_for_activation"
