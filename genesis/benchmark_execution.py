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
    module to edit its own scoring logic.
    """

    def __init__(self, root: Path) -> None:
        self.root = Path(root).resolve()
        self.runtime = self.root / "runtime"
        self.queue = PersistentTaskQueue(self.runtime / "genesis_tasks.sqlite3")
        self.input_dir = self.runtime / "competitive_benchmark_inputs"

    @staticmethod
    def _benchmark_id(task: GenesisTask) -> str:
        benchmark = task.payload.get("benchmark", {}) if isinstance(task.payload, dict) else {}
        return str(benchmark.get("benchmark_id", "")).strip()

    def _runner_task(self, task: GenesisTask, benchmark_id: str) -> dict[str, Any]:
        context = [
            "genesis/competitive_benchmarks.py",
            "genesis/benchmark_evidence.py",
            "genesis/evaluation.py",
            "tests/test_competitive_benchmarks.py",
            "tests/test_benchmark_evidence.py",
        ]
        if benchmark_id == "terminal_bench_2_1":
            context += ["genesis/terminal_bench_evidence.py", "tests/test_terminal_bench_evidence.py"]
        objective = (
            f"Make benchmark {benchmark_id} executable for Genesis using the official/comparable benchmark runner and pinned dataset. "
            "Produce real raw benchmark output with provenance; never invent, estimate, hard-code or self-award a score. "
            "Integrate the smallest reproducible runner/adapter needed so BenchmarkExecutionPlanner can stage independently validated evidence."
        )
        child, created = self.queue.create_unique(
            f"benchmark-runner:{benchmark_id}",
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
            },
        )
        return {"status": "runner_work_queued", "benchmark_id": benchmark_id, "task_id": child.task_id, "created": created}

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
