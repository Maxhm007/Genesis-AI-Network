from __future__ import annotations

import json
from pathlib import Path

from genesis.autonomy_pipeline import PipelineStore
from genesis.capability_evolution import CapabilityEvolutionController
from genesis.modules.task_queue import PersistentTaskQueue


def _reference(root: Path, *, benchmark_id: str = "swe_bench_pro", family: str = "software_engineering", target: float = 80.0) -> None:
    path = root / "config" / "competitive_ai_reference.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "as_of": "2026-08-22",
                "benchmarks": [
                    {
                        "id": benchmark_id,
                        "family": family,
                        "reference_score": target,
                        "unit": "percent",
                        "weight": 10,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )


def _result(root: Path, score: float, *, benchmark_id: str = "swe_bench_pro", measured_at: str = "2026-08-22T00:00:00Z") -> None:
    path = root / "runtime" / "competitive_benchmark_results.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "benchmarks": {
                    benchmark_id: {
                        "score": score,
                        "status": "validated",
                        "provenance": {
                            "source": "test-benchmark-runner",
                            "measured_at": measured_at,
                        },
                    }
                }
            }
        ),
        encoding="utf-8",
    )


def _coding_target(root: Path) -> None:
    path = root / "genesis" / "coding.py"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "from __future__ import annotations\n\n"
        "class CodingCapabilityEngine:\n"
        "    \"\"\"Generate bounded repository changes from verified objectives.\"\"\"\n"
        "    def execute_repository_change(self, objective: str) -> str:\n"
        "        return objective.strip()\n",
        encoding="utf-8",
    )


def _controller(root: Path) -> CapabilityEvolutionController:
    queue = PersistentTaskQueue(root / "runtime" / "genesis_tasks.sqlite3")
    pipeline = PipelineStore(queue.path)
    return CapabilityEvolutionController(root, queue=queue, pipeline=pipeline)


def test_unmeasured_benchmark_creates_measurement_not_blind_capability_growth(tmp_path: Path) -> None:
    _reference(tmp_path)
    _coding_target(tmp_path)
    controller = _controller(tmp_path)

    report = controller.run_once()

    assert report["focus"]["benchmark_id"] == "swe_bench_pro"
    assert report["focus"]["status"] == "unmeasured"
    assert report["growth_work"]["status"] == "measurement_required"
    tasks = controller.queue.list(limit=100)
    assert any(
        task.payload.get("task_type") == "frontier_benchmark_measurement"
        and task.payload.get("benchmark", {}).get("benchmark_id") == "swe_bench_pro"
        for task in tasks
    )
    assert not any(task.payload.get("task_type") == "capability_growth" for task in tasks)


def test_validated_benchmark_deficit_creates_shared_pipeline_growth_work(tmp_path: Path) -> None:
    _reference(tmp_path)
    _result(tmp_path, 32.0)
    _coding_target(tmp_path)
    controller = _controller(tmp_path)

    report = controller.run_once()

    assert report["focus"]["status"] == "measured_below_reference"
    assert report["growth_work"]["status"] == "created"
    task = controller.queue.get(report["growth_work"]["task_id"])
    assert task is not None
    assert task.payload["source"] == "genesis.evolution_learning"
    assert task.payload["task_type"] == "capability_growth"
    assert task.payload["capability_key"] == "software_engineering"
    assert task.payload["benchmark_gap"]["benchmark_id"] == "swe_bench_pro"
    assert task.payload["baseline_score"] == 32.0
    record = controller.pipeline.get(task.task_id)
    assert record is not None
    assert record.stage == "discovered"
    assert record.target_path == "genesis/coding.py"
    assert record.discovery["source"] == "genesis.evolution_learning"
    assert record.discovery["finding"]["confidence_normalized"] == 1.0


def _quarantine(queue: PersistentTaskQueue, key: str, *, generation: int) -> None:
    task = queue.create(
        f"Repeated benchmark capability attempt {generation}",
        module_id="genesis.coding",
        payload={
            "task_type": "capability_growth",
            "capability_key": "software_engineering",
            "capability_generation": generation,
            "benchmark_gap": {
                "benchmark_id": "swe_bench_pro",
                "capability_key": "software_engineering",
            },
            "dedupe_key": key,
        },
        max_attempts=1,
    )
    queue.transition(task.task_id, "assigned", module_id="genesis.coding")
    queue.transition(task.task_id, "running", module_id="genesis.coding")
    queue.record_failure(
        task.task_id,
        "candidate tests failed in repository repair stage 17",
        classification="candidate_test_failure",
        module_id="genesis.coding",
    )


def test_repeated_quarantine_failure_produces_strategy_change_directive(tmp_path: Path) -> None:
    _reference(tmp_path)
    _result(tmp_path, 30.0)
    _coding_target(tmp_path)
    controller = _controller(tmp_path)
    _quarantine(controller.queue, "q1", generation=1)
    _quarantine(controller.queue, "q2", generation=2)

    report = controller.run_once()

    analysis = report["quarantine_analysis"]
    assert analysis["quarantined_tasks"] == 2
    assert analysis["patterns"][0]["count"] == 2
    assert analysis["strategy_directives"]
    assert "do not repeat the same implementation approach" in analysis["strategy_directives"][0]
    growth = controller.queue.get(report["growth_work"]["task_id"])
    assert growth is not None
    assert "FAILURE_STRATEGY:" in growth.objective


def test_completed_growth_requires_post_promotion_remeasurement_and_records_gain(tmp_path: Path) -> None:
    _reference(tmp_path, target=60.0)
    _result(tmp_path, 40.0, measured_at="2999-01-01T00:00:00Z")
    _coding_target(tmp_path)
    controller = _controller(tmp_path)
    gap = {
        "gap_key": "gap-test",
        "benchmark_id": "swe_bench_pro",
        "family": "software_engineering",
        "status": "measured_below_reference",
        "actual_score": 30.0,
        "reference_score": 60.0,
        "unit": "percent",
        "weight": 10,
        "capability_key": "software_engineering",
        "capability_domains": ["coding_engineering"],
        "capability_needs": ["test-grounded patch generation"],
        "target_path": "genesis/coding.py",
        "evidence": "Validated benchmark swe_bench_pro=30/60 percent",
    }
    task = controller.queue.create(
        "Improve measured software engineering benchmark capability.",
        module_id="genesis.coding",
        payload={
            "source": "genesis.evolution_learning",
            "task_type": "capability_growth",
            "capability_key": "software_engineering",
            "capability_generation": 1,
            "benchmark_gap": gap,
            "baseline_score": 30.0,
        },
    )
    controller.queue.transition(task.task_id, "assigned", module_id="genesis.coding")
    controller.queue.transition(task.task_id, "running", module_id="genesis.coding")
    controller.queue.transition(task.task_id, "review", module_id="genesis.coding")
    controller.queue.transition(task.task_id, "complete", module_id="genesis.self_learning")

    report = controller.run_once()

    impact = next(row for row in report["impact_assessments"] if row["growth_task_id"] == task.task_id)
    assert impact["status"] == "improved"
    assert impact["baseline_score"] == 30.0
    assert impact["current_score"] == 40.0
    assert impact["delta"] == 10.0
    assert report["impact_measurement_tasks_created"]
    measurement = controller.queue.get(report["impact_measurement_tasks_created"][0])
    assert measurement is not None
    assert measurement.payload["task_type"] == "frontier_benchmark_measurement"
    assert measurement.payload["impact_of_task_id"] == task.task_id
    assert measurement.payload["score_fabrication_forbidden"] is True
