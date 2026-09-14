from __future__ import annotations

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


def test_swe_bench_pro_runner_context_prioritizes_existing_evidence_adapter(tmp_path: Path) -> None:
    task = make_task(tmp_path, "swe_bench_pro")
    result = BenchmarkExecutionPlanner(tmp_path).advance(task)
    child = BenchmarkExecutionPlanner(tmp_path).queue.get(result["task_id"])
    assert child is not None
    assert child.payload["context_paths"][:4] == [
        "genesis/swe_bench_pro_evidence.py",
        "genesis/benchmark_execution.py",
        "tests/test_swe_bench_pro_evidence.py",
        "tests/test_benchmark_execution.py",
    ]
    readiness = BenchmarkExecutionPlanner._execution_readiness("swe_bench_pro")
    assert readiness == {"ready": True, "missing": [], "benchmark_id": "swe_bench_pro"}


def test_swe_bench_pro_input_is_staged_through_verified_adapter(tmp_path: Path, monkeypatch) -> None:
    task = make_task(tmp_path, "swe_bench_pro")
    planner = BenchmarkExecutionPlanner(tmp_path)
    planner.input_dir.mkdir(parents=True, exist_ok=True)
    (planner.input_dir / "swe_bench_pro.json").write_text(json.dumps({"raw": "official-result"}), encoding="utf-8")
    staged = tmp_path / "runtime" / "staged-swe-bench-pro.json"

    def fake_stage(self, job):
        assert job == {"raw": "official-result"}
        staged.parent.mkdir(parents=True, exist_ok=True)
        staged.write_text("{}", encoding="utf-8")
        return staged

    monkeypatch.setattr("genesis.benchmark_execution.SWEBenchProEvidenceAdapter.stage", fake_stage)
    result = planner.advance(task)
    assert result == {
        "status": "evidence_staged",
        "benchmark_id": "swe_bench_pro",
        "candidate_path": str(staged),
    }
    assert planner._runner_tasks("swe_bench_pro") == []


def test_terminal_bench_input_is_staged_through_verified_adapter(tmp_path: Path, monkeypatch) -> None:
    task = make_task(tmp_path, "terminal_bench_2_1")
    planner = BenchmarkExecutionPlanner(tmp_path)
    planner.input_dir.mkdir(parents=True, exist_ok=True)
    (planner.input_dir / "terminal_bench_2_1.json").write_text(json.dumps({"raw": "terminal-result"}), encoding="utf-8")
    staged = tmp_path / "runtime" / "staged-terminal.json"

    def fake_stage(self, job):
        assert job == {"raw": "terminal-result"}
        staged.parent.mkdir(parents=True, exist_ok=True)
        staged.write_text("{}", encoding="utf-8")
        return staged

    monkeypatch.setattr("genesis.benchmark_execution.TerminalBench21EvidenceAdapter.stage", fake_stage)
    result = planner.advance(task)
    assert result["status"] == "evidence_staged"
    assert result["candidate_path"] == str(staged)


def test_runner_context_is_inside_self_development_sandbox(tmp_path: Path) -> None:
    for benchmark_id in ("terminal_bench_2_1", "agents_last_exam", "swe_bench_pro"):
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
