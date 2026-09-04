from __future__ import annotations

from pathlib import Path

import json

from pathlib import Path
from genesis.benchmark_execution import BenchmarkExecutionPlanner
from genesis.modules.task_queue import PersistentTaskQueue
from genesis.selfdev import normalize_selfdev_path

def make_task(root: Path, benchmark_id: str = "terminal_bench_2_1"):
    queue = PersistentTaskQueue(root / "runtime" / "genesis_tasks.sqlite3")
    return queue.create(
        f"Measure {benchmark_id}",
        module_id="genesis.evaluation",
        priority=92,
        payload={
            "task_type": "frontier_benchmark_measurement",
            "benchmark": {"benchmark_id": benchmark_id},
        },
    )

def quarantine(queue: PersistentTaskQueue, task_id: str) -> None:
    queue.transition(task_id, "assigned", module_id="genesis.coding")
    queue.transition(task_id, "running", module_id="genesis.coding")
    queue.transition(task_id, "failed", module_id="genesis.coding")
    queue.transition(task_id, "quarantined", module_id="genesis.coding")
from genesis.modules.task_queue import PersistentTaskQueue
from genesis.selfdev import normalize_selfdev_path


def make_task(root: Path, benchmark_id: str = "terminal_bench_2_1"):
    queue = PersistentTaskQueue(root / "runtime" / "genesis_tasks.sqlite3")
    return queue.create(
        f"Measure {benchmark_id}",
        module_id="genesis.evaluation",
        priority=92,
        payload={
            "task_type": "frontier_benchmark_measurement",
            "benchmark": {"benchmark_id": benchmark_id},
        },
    )


def quarantine(queue: PersistentTaskQueue, task_id: str) -> None:
    queue.transition(task_id, "assigned", module_id="genesis.coding")
    queue.transition(task_id, "running", module_id="genesis.coding")
    queue.transition(task_id, "failed", module_id="genesis.coding")
    queue.transition(task_id, "quarantined", module_id="genesis.coding")


def test_missing_real_result_creates_one_runner_task(tmp_path: Path) -> None:
    task = make_task(tmp_path)
    planner = BenchmarkExecutionPlanner(tmp_path)
    first = planner.advance(task)
    second = planner.advance(task)
    assert first["status"] == "runner_work_queued"
    assert first["created"] is True
    assert second["created"] is False
    assert first["task_id"] == second["task_id"]
    child = planner.queue.get(first["task_id"])
    assert child is not None
    assert child.module_id == "genesis.coding"
    assert child.payload["score_fabrication_forbidden"] is True
    assert "genesis/terminal_bench_evidence.py" in child.payload["context_paths"]


def test_terminal_runner_context_prioritizes_editable_executable_files(tmp_path: Path) -> None:
    task = make_task(tmp_path)
    result = BenchmarkExecutionPlanner(tmp_path).advance(task)
    child = BenchmarkExecutionPlanner(tmp_path).queue.get(result["task_id"])
    assert child is not None
    assert child.payload["context_paths"][:4] == [
        "genesis/terminal_bench_evidence.py",
        "genesis/benchmark_execution.py",
        "tests/test_terminal_bench_evidence.py",
        "tests/test_benchmark_execution.py",
    ]


def test_runner_context_is_inside_self_development_sandbox(tmp_path: Path) -> None:
    for benchmark_id in ("terminal_bench_2_1", "agents_last_exam"):
        context = BenchmarkExecutionPlanner._runner_context(benchmark_id)
        assert context
        for path in context:
            assert normalize_selfdev_path(tmp_path, path) == path


def test_exhausted_terminal_runner_work_surfaces_execution_readiness_blocker(tmp_path: Path, monkeypatch) -> None:
    for name in BenchmarkExecutionPlanner.TERMINAL_BENCH_ENV:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr("genesis.benchmark_execution.shutil.which", lambda _: None)

    task = make_task(tmp_path)
    planner = BenchmarkExecutionPlanner(tmp_path)
    for expected in range(1, BenchmarkExecutionPlanner.MAX_RUNNER_INTEGRATION_GENERATIONS + 1):
        attempt = planner.advance(task)
        assert attempt["status"] == "runner_work_queued"
        assert attempt["work_generation"] == expected
        quarantine(planner.queue, attempt["task_id"])

    result = planner.advance(task)
    assert result["status"] == "external_execution_required"
    assert result["owner_action_required"] is True
    assert result["last_work_generation"] == BenchmarkExecutionPlanner.MAX_RUNNER_INTEGRATION_GENERATIONS
    assert "harbor_cli" in result["missing"]
    assert "GENESIS_BENCHMARK_MODEL" in result["missing"]
    assert len(planner._runner_tasks("terminal_bench_2_1")) == BenchmarkExecutionPlanner.MAX_RUNNER_INTEGRATION_GENERATIONS


def test_unknown_benchmark_still_queues_bounded_runner_work(tmp_path: Path) -> None:
    task = make_task(tmp_path, "new_frontier_benchmark")
    result = BenchmarkExecutionPlanner(tmp_path).advance(task)
    assert result["status"] == "runner_work_queued"
    child = BenchmarkExecutionPlanner(tmp_path).queue.get(result["task_id"])
    assert child is not None
    assert child.payload["benchmark_id"] == "new_frontier_benchmark"
    assert child.payload["requires_independent_validation"] is True
    assert child.payload["context_paths"][:4] == [
        "genesis/benchmark_execution.py",
        "genesis/benchmark_evidence.py",
        "tests/test_benchmark_execution.py",
        "genesis/competitive_benchmarks.py",
    ]


def test_unknown_benchmark_stops_after_bounded_runner_generations(tmp_path: Path) -> None:
    task = make_task(tmp_path, "new_frontier_benchmark")
    planner = BenchmarkExecutionPlanner(tmp_path)

    for expected in range(1, BenchmarkExecutionPlanner.MAX_RUNNER_INTEGRATION_GENERATIONS + 1):
        attempt = planner.advance(task)
        assert attempt["status"] == "runner_work_queued"
        assert attempt["work_generation"] == expected
        quarantine(planner.queue, attempt["task_id"])

    result = planner.advance(task)
    assert result["status"] == "runner_integration_exhausted"
    assert result["engineering_assistance_required"] is True
    assert result["owner_action_required"] is False
    assert result["last_work_generation"] == BenchmarkExecutionPlanner.MAX_RUNNER_INTEGRATION_GENERATIONS
    assert result["missing"] == ["benchmark_specific_evidence_adapter"]
    assert len(planner._runner_tasks("new_frontier_benchmark")) == BenchmarkExecutionPlanner.MAX_RUNNER_INTEGRATION_GENERATIONS


def test_invalid_evaluation_task_does_not_create_work(tmp_path: Path) -> None:
    queue = PersistentTaskQueue(tmp_path / "runtime" / "genesis_tasks.sqlite3")
    task = queue.create("Measure something", module_id="genesis.evaluation", payload={})
    planner = BenchmarkExecutionPlanner(tmp_path)
    result = planner.advance(task)
    assert result["status"] == "invalid_task"
    assert len(planner.queue.list(limit=20)) == 1
