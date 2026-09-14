from pathlib import Path

from genesis.benchmark_cycle import advance_one_benchmark
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


def runner_tasks(queue: PersistentTaskQueue, benchmark_id: str):
    return [
        item
        for item in queue.list(limit=100)
        if item.payload.get("task_type") == "benchmark_runner_integration"
        and item.payload.get("benchmark_id") == benchmark_id
    ]


def test_benchmark_cycle_records_measurement_as_performance_indicator(tmp_path: Path) -> None:
    queue, task = make_evaluation(tmp_path)

    result = advance_one_benchmark(tmp_path)

    assert result["status"] == "performance_indicator_recorded"
    assert task.task_id in result["task_ids"]
    updated = queue.get(task.task_id)
    assert updated.state == "cancelled"
    assert updated.state_reason.startswith("performance_indicator:")
    assert runner_tasks(queue, "terminal_bench_2_1") == []


def test_multiple_measurements_are_terminalized_without_solver_work(tmp_path: Path) -> None:
    queue, first = make_evaluation(tmp_path, "terminal_bench_2_1")
    _, second = make_evaluation(tmp_path, "swe_bench_pro")

    result = advance_one_benchmark(tmp_path)

    assert result["status"] == "performance_indicator_recorded"
    assert set(result["task_ids"]) == {first.task_id, second.task_id}
    assert queue.get(first.task_id).state == "cancelled"
    assert queue.get(second.task_id).state == "cancelled"
    assert runner_tasks(queue, "terminal_bench_2_1") == []
    assert runner_tasks(queue, "swe_bench_pro") == []


def test_external_benchmark_measurement_is_not_an_actionable_blocker(tmp_path: Path) -> None:
    queue, task = make_evaluation(tmp_path, "agents_last_exam")

    result = advance_one_benchmark(tmp_path)

    assert result["status"] == "performance_indicator_recorded"
    updated = queue.get(task.task_id)
    assert updated.state == "cancelled"
    assert "measurement/reporting work" in updated.state_reason
    assert runner_tasks(queue, "agents_last_exam") == []


def test_second_cycle_is_idle_after_indicator_recorded(tmp_path: Path) -> None:
    queue, task = make_evaluation(tmp_path, "swe_bench_pro")

    first = advance_one_benchmark(tmp_path)
    second = advance_one_benchmark(tmp_path)

    assert first["status"] == "performance_indicator_recorded"
    assert second["status"] == "idle"
    assert queue.get(task.task_id).state == "cancelled"


def test_performance_indicator_never_creates_runner_generation(tmp_path: Path) -> None:
    queue, task = make_evaluation(tmp_path, "swe_bench_pro")

    result = advance_one_benchmark(tmp_path)

    assert result["status"] == "performance_indicator_recorded"
    assert queue.get(task.task_id).state == "cancelled"
    assert runner_tasks(queue, "swe_bench_pro") == []


def test_indicator_result_includes_terminalization_evidence(tmp_path: Path) -> None:
    queue, task = make_evaluation(tmp_path, "terminal_bench_2_1")

    result = advance_one_benchmark(tmp_path)

    evidence = result["performance_indicators"]
    assert len(evidence) == 1
    assert evidence[0]["task_id"] == task.task_id
    assert evidence[0]["task_type"] == "frontier_benchmark_measurement"
    assert evidence[0]["state"] == "cancelled"
    assert evidence[0]["reason"].startswith("performance_indicator:")
    assert queue.get(task.task_id).state == "cancelled"
