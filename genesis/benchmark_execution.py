from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .modules.task_queue import GenesisTask, PersistentTaskQueue
from .terminal_bench_evidence import TerminalBench21EvidenceAdapter


class BenchmarkExecutionPlanner:
    """Advance frontier benchmark tasks without fabricating capability evidence.

    Real benchmark output may be staged only through a benchmark-specific evidence
    adapter. If no real result is available, the planner creates one durable coding
    task for the missing runner/integration instead of repeatedly asking the AI score
    module to edit its own scoring logic. Exhausted runner work may advance to a new
    bounded generation, preserving auditability without looping forever on one task.
    """

    TERMINAL_RUNNER_STATES = {"complete", "quarantined", "cancelled"}

    def __init__(self, root: Path) -> None:
        self.root = Path(root).resolve()
        self.runtime = self.root / "runtime"
        self.queue = PersistentTaskQueue(self.runtime / "genesis_tasks.sqlite3")
        self.input_dir = self.runtime / "competitive_benchmark_inputs"

    @staticmethod
    def _benchmark_id(task: GenesisTask) -> str:
        benchmark = task.payload.get("benchmark", {}) if isinstance(task.payload, dict) else {}
        return str(benchmark.get("benchmark_id", "")).strip()

    def _runner_tasks(self, benchmark_id: str) -> list[GenesisTask]:
        return [
            task
            for task in self.queue.list(limit=5000)
            if task.payload.get("task_type") == "benchmark_runner_integration"
            and str(task.payload.get("benchmark_id", "")) == benchmark_id
        ]

    @staticmethod
    def _runner_generation(task: GenesisTask) -> int:
        try:
            return max(1, int(task.payload.get("work_generation", 1)))
        except Exception:
            return 1

    def _runner_task(self, task: GenesisTask, benchmark_id: str) -> dict[str, Any]:
        context = [
            "genesis/competitive_benchmarks.py",
            "genesis/benchmark_execution.py",
            "genesis/benchmark_evidence.py",
            "genesis/evaluation.py",
            "scripts/benchmark_task_worker.py",
            "tests/test_competitive_benchmarks.py",
            "tests/test_benchmark_execution.py",
            "tests/test_benchmark_evidence.py",
        ]
        if benchmark_id == "terminal_bench_2_1":
            context += ["genesis/terminal_bench_evidence.py", "tests/test_terminal_bench_evidence.py"]

        existing = self._runner_tasks(benchmark_id)
        latest = max(existing, key=self._runner_generation) if existing else None
        if latest is not None and latest.state not in self.TERMINAL_RUNNER_STATES:
            return {
                "status": "runner_work_queued",
                "benchmark_id": benchmark_id,
                "task_id": latest.task_id,
                "created": False,
                "work_generation": self._runner_generation(latest),
                "runner_state": latest.state,
            }

        generation = self._runner_generation(latest) + 1 if latest is not None else 1
        objective = (
            f"Make benchmark {benchmark_id} executable for Genesis using the official/comparable benchmark runner and pinned dataset. "
            "Produce real raw benchmark output with provenance; never invent, estimate, hard-code or self-award a score. "
            "Integrate the smallest reproducible runner/adapter needed so BenchmarkExecutionPlanner can stage independently validated evidence."
        )
        dedupe_key = f"benchmark-runner:{benchmark_id}" if generation == 1 else f"benchmark-runner:{benchmark_id}:generation:{generation}"
        child, created = self.queue.create_unique(
            dedupe_key,
            objective,
            module_id="genesis.coding",
            priority=max(task.priority, 93),
            payload={
                "task_type": "benchmark_runner_integration",
                "benchmark_id": benchmark_id,
                "parent_task_id": task.task_id,
                "context_paths": context,
                "score_fabrication_forbidden": True,
                "requires_independent_validation": True,
                "work_generation": generation,
            },
        )
        return {
            "status": "runner_work_queued",
            "benchmark_id": benchmark_id,
            "task_id": child.task_id,
            "created": created,
            "work_generation": generation,
            "runner_state": child.state,
        }

    def advance(self, task: GenesisTask) -> dict[str, Any]:
        benchmark_id = self._benchmark_id(task)
        if not benchmark_id:
            return {"status": "invalid_task", "reason": "benchmark_id missing", "task": asdict(task)}

        input_path = self.input_dir / f"{benchmark_id}.json"
        if benchmark_id == "terminal_bench_2_1" and input_path.is_file():
            job = json.loads(input_path.read_text(encoding="utf-8"))
            staged = TerminalBench21EvidenceAdapter(self.root).stage(job)
            return {"status": "evidence_staged", "benchmark_id": benchmark_id, "candidate_path": str(staged)}

        return self._runner_task(task, benchmark_id)
