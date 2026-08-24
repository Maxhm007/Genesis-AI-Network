from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .modules.task_queue import GenesisTask, PersistentTaskQueue


@dataclass(frozen=True)
class BenchmarkGap:
    benchmark_id: str
    family: str
    reference_score: float
    unit: str
    weight: int

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


class CompetitiveBenchmarkPlanner:
    """Turn unmeasured frontier benchmark families into durable evaluation work.

    This planner never fabricates scores and never treats architecture or a model
    name as benchmark evidence. A benchmark stops being a gap only when runtime
    results contain a score plus explicit provenance and validated status.
    """

    TERMINAL_TASK_STATES = {"complete", "quarantined", "cancelled"}

    def __init__(self, root: Path) -> None:
        self.root = Path(root).resolve()
        self.reference_path = self.root / "config" / "competitive_ai_reference.json"
        self.results_path = self.root / "runtime" / "competitive_benchmark_results.json"
        self.queue = PersistentTaskQueue(self.root / "runtime" / "genesis_tasks.sqlite3")

    def _reference(self) -> dict[str, Any]:
        if not self.reference_path.exists():
            return {"benchmarks": []}
        return json.loads(self.reference_path.read_text(encoding="utf-8"))

    def _results(self) -> dict[str, Any]:
        if not self.results_path.exists():
            return {"benchmarks": {}}
        try:
            return json.loads(self.results_path.read_text(encoding="utf-8"))
        except Exception:
            return {"benchmarks": {}}

    @staticmethod
    def is_validated_measurement(result: object) -> bool:
        if not isinstance(result, dict):
            return False
        if "score" not in result:
            return False
        if str(result.get("status", "")).lower() != "validated":
            return False
        provenance = result.get("provenance")
        if not isinstance(provenance, dict):
            return False
        return bool(str(provenance.get("source", "")).strip() and str(provenance.get("measured_at", "")).strip())

    def missing(self) -> list[BenchmarkGap]:
        results = self._results().get("benchmarks", {})
        gaps: list[BenchmarkGap] = []
        for item in self._reference().get("benchmarks", []):
            benchmark_id = str(item["id"])
            if self.is_validated_measurement(results.get(benchmark_id)):
                continue
            gaps.append(BenchmarkGap(
                benchmark_id=benchmark_id,
                family=str(item.get("family", benchmark_id)),
                reference_score=float(item.get("reference_score", 0.0)),
                unit=str(item.get("unit", "score")),
                weight=int(item.get("weight", 0)),
            ))
        return gaps

    @staticmethod
    def _work_generation(task: GenesisTask) -> int:
        try:
            return max(1, int(task.payload.get("work_generation", 1)))
        except Exception:
            return 1

    def _tasks_for_benchmark(self, benchmark_id: str) -> list[GenesisTask]:
        return [
            task
            for task in self.queue.list(limit=5000)
            if task.module_id == "genesis.evaluation"
            and task.payload.get("task_type") == "frontier_benchmark_measurement"
            and str(dict(task.payload.get("benchmark") or {}).get("benchmark_id") or "") == benchmark_id
        ]

    def _is_live_task(self, task: GenesisTask) -> bool:
        if task.state in self.TERMINAL_TASK_STATES:
            return False
        if task.state == "failed" and not self.queue.retryable(task):
            return False
        return True

    def _ensure_gap_task(self, gap: BenchmarkGap, objective: str) -> tuple[GenesisTask, bool]:
        existing = self._tasks_for_benchmark(gap.benchmark_id)
        live = [task for task in existing if self._is_live_task(task)]
        if live:
            live.sort(key=lambda task: (-int(task.priority), task.created_at, task.task_id))
            return live[0], False

        generation = max((self._work_generation(task) for task in existing), default=0) + 1
        base_key = f"frontier-benchmark:{gap.benchmark_id}"
        dedupe_key = base_key if generation == 1 else f"{base_key}:generation:{generation}"
        return self.queue.create_unique(
            dedupe_key,
            objective,
            module_id="genesis.evaluation",
            priority=92,
            payload={
                "task_type": "frontier_benchmark_measurement",
                "benchmark": gap.as_dict(),
                "requires_provenance": True,
                "requires_independent_validation": True,
                "score_fabrication_forbidden": True,
                "work_generation": generation,
                "strategy_change_required": generation > 1,
            },
        )

    def ensure_tasks(self) -> dict[str, Any]:
        created: list[str] = []
        task_ids: list[str] = []
        gaps = self.missing()
        for gap in gaps:
            objective = (
                f"Measure Genesis on frontier benchmark {gap.benchmark_id} ({gap.family}) using a comparable, reproducible evaluation. "
                "Record the real measured score only with source provenance, measurement timestamp, runner/config details, and independent validation. "
                "Do not estimate or infer benchmark credit from architecture or model identity."
            )
            task, was_created = self._ensure_gap_task(gap, objective)
            task_ids.append(task.task_id)
            if was_created:
                created.append(task.task_id)
        return {
            "missing_count": len(gaps),
            "missing_benchmarks": [gap.as_dict() for gap in gaps],
            "task_ids": task_ids,
            "created_task_ids": created,
        }
