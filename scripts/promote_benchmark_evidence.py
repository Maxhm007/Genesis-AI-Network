from __future__ import annotations

import argparse
import json
from pathlib import Path

from genesis.benchmark_evidence_validation import promote_candidate
from genesis.capability_evolution import CapabilityEvolutionController
from genesis.modules.task_queue import PersistentTaskQueue


def _benchmark_id(task) -> str:
    payload = dict(task.payload or {})
    benchmark = payload.get("benchmark")
    if isinstance(benchmark, dict):
        return str(benchmark.get("benchmark_id") or "").strip()
    return str(payload.get("benchmark_id") or "").strip()


def _complete_measurement_tasks(root: Path, benchmark_id: str) -> list[str]:
    queue = PersistentTaskQueue(root / "runtime" / "genesis_tasks.sqlite3")
    completed: list[str] = []
    for task in queue.list(limit=5000):
        if task.payload.get("task_type") != "frontier_benchmark_measurement":
            continue
        if _benchmark_id(task) != benchmark_id:
            continue
        if task.state in {"complete", "cancelled", "quarantined"}:
            continue
        current = task
        if current.state == "new":
            current = queue.transition(current.task_id, "assigned", module_id="genesis.evaluation")
        elif current.state == "failed":
            current = queue.transition(current.task_id, "assigned", module_id="genesis.evaluation")
        if current.state in {"assigned", "paused", "blocked"}:
            current = queue.transition(current.task_id, "running", module_id="genesis.evaluation")
        if current.state == "running":
            current = queue.transition(current.task_id, "review", module_id="genesis.evaluation")
        if current.state == "review":
            current = queue.transition(current.task_id, "complete", module_id="genesis.evaluation")
        if current.state == "complete":
            completed.append(current.task_id)
    return completed


def main() -> None:
    parser = argparse.ArgumentParser(description="Promote independently validated Genesis benchmark evidence")
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--vote", action="append", required=True)
    parser.add_argument("--output", default="runtime/benchmark_promotion.json")
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    promoted = promote_candidate(
        root,
        Path(args.candidate),
        [Path(value) for value in args.vote],
        minimum_validators=2,
    )
    benchmark_id = str(promoted["benchmark_id"])
    completed_tasks = _complete_measurement_tasks(root, benchmark_id)
    evolution = CapabilityEvolutionController(root).run_once()
    payload = {
        "status": "validated_benchmark_promoted",
        "benchmark": promoted,
        "completed_measurement_tasks": completed_tasks,
        "capability_evolution": {
            "focus": evolution.get("focus"),
            "growth_work": evolution.get("growth_work"),
        },
    }
    output = root / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
