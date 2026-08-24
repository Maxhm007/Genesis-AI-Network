from __future__ import annotations

import json
from pathlib import Path

from genesis.autonomy_pipeline import PipelineStore
from genesis.capability_evolution import CapabilityEvolutionController
from genesis.modules.task_queue import PersistentTaskQueue


def _setup(root: Path) -> CapabilityEvolutionController:
    config = root / "config" / "competitive_ai_reference.json"
    config.parent.mkdir(parents=True, exist_ok=True)
    config.write_text(
        json.dumps(
            {
                "as_of": "2026-08-24",
                "benchmarks": [
                    {
                        "id": "swe_bench_pro",
                        "family": "software_engineering",
                        "reference_score": 80.3,
                        "unit": "percent",
                        "weight": 10,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    results = root / "runtime" / "competitive_benchmark_results.json"
    results.parent.mkdir(parents=True, exist_ok=True)
    results.write_text(
        json.dumps(
            {
                "benchmarks": {
                    "swe_bench_pro": {
                        "score": 0.0,
                        "status": "validated",
                        "provenance": {
                            "source": "test-benchmark-runner",
                            "measured_at": "2026-08-24T00:00:00Z",
                        },
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    target = root / "genesis" / "coding.py"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        "from __future__ import annotations\n\n"
        "class CodingCapabilityEngine:\n"
        "    \"\"\"Generate bounded repository changes from verified objectives.\"\"\"\n"
        "    def execute_repository_change(self, objective: str) -> str:\n"
        "        return objective.strip()\n",
        encoding="utf-8",
    )
    queue = PersistentTaskQueue(root / "runtime" / "genesis_tasks.sqlite3")
    pipeline = PipelineStore(queue.path)
    return CapabilityEvolutionController(root, queue=queue, pipeline=pipeline)


def _quarantined_growth(controller: CapabilityEvolutionController) -> str:
    task = controller.queue.create(
        "Improve measured SWE-Bench capability generation 1.",
        module_id="genesis.coding",
        priority=95,
        payload={
            "task_type": "capability_growth",
            "capability_key": "software_engineering",
            "capability_generation": 1,
            "benchmark_gap": {
                "benchmark_id": "swe_bench_pro",
                "capability_key": "software_engineering",
            },
            "dedupe_key": "capability-growth:swe_bench_pro:generation:1",
        },
        max_attempts=1,
    )
    controller.queue.transition(task.task_id, "assigned", module_id="genesis.coding")
    controller.queue.transition(task.task_id, "running", module_id="genesis.coding")
    controller.queue.record_failure(
        task.task_id,
        "bounded provider proposal failed syntax validation",
        classification="pipeline_development",
        module_id="genesis.coding",
    )
    assert controller.queue.get(task.task_id).state == "quarantined"
    return task.task_id


def test_quarantined_measured_growth_creates_next_generation_despite_unrelated_active_pipeline(tmp_path: Path) -> None:
    controller = _setup(tmp_path)
    previous_task_id = _quarantined_growth(controller)

    speculative = controller.queue.create(
        "Explore an unrelated speculative learned capability.",
        module_id="genesis.coding",
        priority=78,
        payload={
            "task_type": "new_capability",
            "target_path": "genesis/learned_capabilities.py",
        },
    )
    controller.pipeline.register_discovery(
        speculative.task_id,
        "genesis/learned_capabilities.py",
        {
            "status": "new_capability_enqueued",
            "source": "test.research",
            "finding": {
                "decision": "upgrade",
                "new_capability": True,
                "target_path": "genesis/learned_capabilities.py",
            },
        },
    )
    assert controller.pipeline.list_active()

    report = controller.run_once()

    growth = report["growth_work"]
    assert growth["status"] == "created"
    assert growth["capability_generation"] == 2
    assert growth["readiness_reason"] == "previous_growth_quarantined"
    assert speculative.task_id in growth["concurrent_pipeline_task_ids"]

    next_task = controller.queue.get(growth["task_id"])
    assert next_task is not None
    assert next_task.task_id != previous_task_id
    assert next_task.payload["task_type"] == "capability_growth"
    assert next_task.payload["capability_generation"] == 2
    assert next_task.priority == 95

    # The unrelated pipeline record is not cancelled or promoted by this controller;
    # normal scheduling/review gates decide execution order.
    speculative_record = controller.pipeline.get(speculative.task_id)
    assert speculative_record is not None
    assert speculative_record.stage == "discovered"
