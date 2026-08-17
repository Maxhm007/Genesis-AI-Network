from __future__ import annotations

import json
from pathlib import Path

from genesis.competitive_benchmarks import CompetitiveBenchmarkPlanner


def write_reference(root: Path) -> None:
    (root / "config").mkdir(parents=True)
    data = {"benchmarks": [
        {"id": "bench_a", "family": "reasoning", "reference_score": 80, "unit": "percent", "weight": 10},
        {"id": "bench_b", "family": "coding", "reference_score": 70, "unit": "percent", "weight": 10},
    ]}
    (root / "config" / "competitive_ai_reference.json").write_text(json.dumps(data), encoding="utf-8")


def test_missing_benchmarks_create_tasks(tmp_path: Path) -> None:
    write_reference(tmp_path)
    planner = CompetitiveBenchmarkPlanner(tmp_path)
    report = planner.ensure_tasks()
    assert report["missing_count"] == 2
    assert len(report["created_task_ids"]) == 2
    tasks = planner.queue.list(limit=10)
    assert {task.module_id for task in tasks} == {"genesis.evaluation"}


def test_validated_measurement_closes_gap(tmp_path: Path) -> None:
    write_reference(tmp_path)
    runtime = tmp_path / "runtime"
    runtime.mkdir(parents=True)
    results = {"benchmarks": {
        "bench_a": {"score": 50, "status": "candidate", "provenance": {"source": "runner", "measured_at": "2026-08-17T00:00:00Z"}},
        "bench_b": {"score": 60, "status": "validated", "provenance": {"source": "runner", "measured_at": "2026-08-17T00:00:00Z"}},
    }}
    (runtime / "competitive_benchmark_results.json").write_text(json.dumps(results), encoding="utf-8")
    gaps = CompetitiveBenchmarkPlanner(tmp_path).missing()
    assert [gap.benchmark_id for gap in gaps] == ["bench_a"]
