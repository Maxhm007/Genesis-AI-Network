from __future__ import annotations

from pathlib import Path

from genesis.model_scout import ModelCandidate, ModelScoutModule
from genesis.modules.task_queue import PersistentTaskQueue
from genesis.task_router import ACTIVE_TASK_LIMIT, TaskRouterModule


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
    assert todo["active"] == 1
    assert todo["active_limit"] == 3


def test_task_router_keeps_three_active_slots_without_replacing_running_work(tmp_path: Path):
    queue = PersistentTaskQueue(tmp_path / "runtime" / "genesis_tasks.sqlite3")
    active_ids = []
    for index in range(ACTIVE_TASK_LIMIT):
        task = queue.create(f"Active task {index}", priority=90 - index)
        queue.transition(task.task_id, "assigned")
        if index == 0:
            queue.transition(task.task_id, "running")
        active_ids.append(task.task_id)
    waiting = queue.create("Waiting task", priority=100)

    result = TaskRouterModule(tmp_path).assign_next()

    assert result["status"] == "active_slots_full"
    assert result["active"] == 3
    assert set(result["active_task_ids"]) == set(active_ids)
    assert queue.get(waiting.task_id).state == "new"
    assert queue.get(active_ids[0]).state == "running"


def test_paused_task_frees_active_slot_but_remains_durable(tmp_path: Path):
    queue = PersistentTaskQueue(tmp_path / "runtime" / "genesis_tasks.sqlite3")
    tasks = []
    for index in range(ACTIVE_TASK_LIMIT):
        task = queue.create(f"Task {index}", priority=80 - index)
        queue.transition(task.task_id, "assigned")
        tasks.append(task)
    queue.pause(tasks[0].task_id, "Owner requested hold")
    waiting = queue.create("Replacement slot task", priority=99)

    result = TaskRouterModule(tmp_path).assign_next()

    assert result["status"] == "assigned"
    assert result["task"]["task_id"] == waiting.task_id
    assert queue.get(tasks[0].task_id).state == "paused"
    assert queue.get(tasks[0].task_id).state_reason == "Owner requested hold"


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
