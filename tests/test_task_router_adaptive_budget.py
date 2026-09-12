from pathlib import Path

from genesis.task_router import ACTIVE_TASK_LIMIT, TaskRouterModule, adaptive_active_task_limit


def _fail_task(router: TaskRouterModule, objective: str):
    task = router.queue.create(objective, module_id="genesis.coding")
    router.queue.transition(task.task_id, "assigned")
    router.queue.transition(task.task_id, "running")
    return router.queue.record_failure(task.task_id, "bounded test failure", retry_after_seconds=0)


def test_healthy_queue_keeps_existing_maximum(tmp_path: Path) -> None:
    router = TaskRouterModule(tmp_path)
    router.queue.create("healthy task one")
    router.queue.create("healthy task two")
    assert adaptive_active_task_limit(router.pending()) == ACTIVE_TASK_LIMIT == 3


def test_single_failure_pressure_reduces_budget_to_two(tmp_path: Path) -> None:
    router = TaskRouterModule(tmp_path)
    _fail_task(router, "repair one")
    router.queue.create("healthy task one")
    router.queue.create("healthy task two")
    assert adaptive_active_task_limit(router.pending()) == 2


def test_multiple_failure_pressure_reduces_budget_to_one(tmp_path: Path) -> None:
    router = TaskRouterModule(tmp_path)
    _fail_task(router, "repair one")
    _fail_task(router, "repair two")
    router.queue.create("healthy task")
    assert adaptive_active_task_limit(router.pending()) == 1
