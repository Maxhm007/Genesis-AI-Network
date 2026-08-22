from pathlib import Path

from genesis.benchmark_cycle import advance_one_benchmark
from genesis.benchmark_execution import BenchmarkExecutionPlanner
from genesis.modules.task_queue import PersistentTaskQueue


def make_evaluation(root: Path, benchmark_id: str = "terminal_bench_2_1"):
    queue = PersistentTaskQueue(root / "runtime" / "genesis_tasks.sqlite3")
    task = queue.create(
        f"Measure {benchmark_id} with real provenance.",
        module_id="genesis.evaluation",
        priority=92,
        payload={
            "task_type": "frontier_benchmark_measurement",
            "benchmark": {"benchmark_id": benchmark_id},
        },
    )
    return queue, task


def quarantine_runner(queue: PersistentTaskQueue, task_id: str) -> None:
    queue.transition(task_id, "assigned", module_id="genesis.coding")
    queue.transition(task_id, "running", module_id="genesis.coding")
    queue.transition(task_id, "failed", module_id="genesis.coding")
    queue.transition(task_id, "quarantined", module_id="genesis.coding")


def test_benchmark_cycle_queues_runner_and_pauses_evaluation(tmp_path: Path) -> None:
    queue, task = make_evaluation(tmp_path)
    result = advance_one_benchmark(tmp_path)
    assert result["status"] == "runner_work_queued"
    assert result["task_id"] == task.task_id
    assert queue.get(task.task_id).state == "paused"
    runner = queue.get(result["result"]["task_id"])
    assert runner.module_id == "genesis.coding"
    assert runner.payload["work_generation"] == 1


def test_benchmark_cycle_prioritizes_fresh_measurement_over_paused_one(tmp_path: Path) -> None:
    queue, first_task = make_evaluation(tmp_path, "terminal_bench_2_1")
    first = advance_one_benchmark(tmp_path)
    assert first["task_id"] == first_task.task_id
    assert queue.get(first_task.task_id).state == "paused"

    second_task = queue.create(
        "Measure another frontier benchmark.",
        module_id="genesis.evaluation",
        priority=92,
        payload={
            "task_type": "frontier_benchmark_measurement",
            "benchmark": {"benchmark_id": "swe_bench_pro"},
        },
    )

    second = advance_one_benchmark(tmp_path)
    assert second["task_id"] == second_task.task_id
    assert second["status"] == "runner_work_queued"


def test_benchmark_cycle_surfaces_durable_external_blocker_after_bounded_runner_work(
    tmp_path: Path, monkeypatch
) -> None:
    for name in BenchmarkExecutionPlanner.TERMINAL_BENCH_ENV:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr("genesis.benchmark_execution.shutil.which", lambda _: None)

    queue, task = make_evaluation(tmp_path)
    first = advance_one_benchmark(tmp_path)
    quarantine_runner(queue, first["result"]["task_id"])

    second = advance_one_benchmark(tmp_path)
    assert second["result"]["work_generation"] == 2
    quarantine_runner(queue, second["result"]["task_id"])

    third = advance_one_benchmark(tmp_path)
    assert third["status"] == "external_execution_required"
    blocked = queue.get(task.task_id)
    assert blocked.state == "paused"
    assert blocked.state_reason.startswith("External authority required for real benchmark execution:")
    assert "harbor_cli" in blocked.state_reason


def test_benchmark_cycle_pauses_when_runner_integration_is_exhausted(tmp_path: Path) -> None:
    queue, task = make_evaluation(tmp_path, "swe_bench_pro")
    first = advance_one_benchmark(tmp_path)
    quarantine_runner(queue, first["result"]["task_id"])

    second = advance_one_benchmark(tmp_path)
    quarantine_runner(queue, second["result"]["task_id"])

    third = advance_one_benchmark(tmp_path)
    assert third["status"] == "runner_integration_exhausted"
    blocked = queue.get(task.task_id)
    assert blocked.state == "paused"
    assert blocked.state_reason.startswith("Bounded benchmark runner integration is exhausted.")
    runner_tasks = [
        item
        for item in queue.list(limit=100)
        if item.payload.get("task_type") == "benchmark_runner_integration"
        and item.payload.get("benchmark_id") == "swe_bench_pro"
    ]
    assert len(runner_tasks) == 2
