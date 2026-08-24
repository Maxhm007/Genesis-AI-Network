from __future__ import annotations

import json
import os
import shutil
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .agents_last_exam_evidence import AgentsLastExamEvidenceAdapter
from .modules.task_queue import GenesisTask, PersistentTaskQueue
from .terminal_bench_evidence import TerminalBench21EvidenceAdapter


class BenchmarkExecutionPlanner:
    """Advance frontier benchmark tasks without fabricating capability evidence.

    Real benchmark output may be staged only through a benchmark-specific evidence
    adapter. If no real result is available, the planner creates bounded coding
    work for missing runner integration. Once that bounded lane is exhausted, an
    execution/readiness blocker is surfaced instead of endlessly generating code.
    """

    TERMINAL_RUNNER_STATES = {"complete", "quarantined", "cancelled"}
    MAX_RUNNER_INTEGRATION_GENERATIONS = 4
    EVIDENCE_ADAPTER_BENCHMARKS = {"agents_last_exam", "terminal_bench_2_1"}
    TERMINAL_BENCH_ENV = (
        "GENESIS_BENCHMARK_AGENT",
        "GENESIS_BENCHMARK_MODEL",
        "GENESIS_BENCHMARK_SANDBOX",
    )

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

    @classmethod
    def _execution_readiness(cls, benchmark_id: str) -> dict[str, Any]:
        if benchmark_id != "terminal_bench_2_1":
            return {
                "ready": benchmark_id in cls.EVIDENCE_ADAPTER_BENCHMARKS,
                "missing": [] if benchmark_id in cls.EVIDENCE_ADAPTER_BENCHMARKS else ["benchmark_specific_evidence_adapter"],
                "benchmark_id": benchmark_id,
            }
        missing: list[str] = []
        if shutil.which("harbor") is None:
            missing.append("harbor_cli")
        for name in cls.TERMINAL_BENCH_ENV:
            if not str(os.environ.get(name, "")).strip():
                missing.append(name)
        return {
            "ready": not missing,
            "missing": missing,
            "benchmark_id": benchmark_id,
            "provider_independent": True,
            "required_trials_per_task": 5,
            "dataset": "terminal-bench/terminal-bench-2-1",
        }

    @staticmethod
    def _runner_context(benchmark_id: str) -> list[str]:
        """Order editable context by execution value because autonomous Coding is bounded.

        Context supplied to autonomous coding must remain inside the self-development
        sandbox. Workflow/entry-point scripts may be useful for humans to inspect,
        but including an uneditable `scripts/` path can make Coding choose it as the
        proposal target and fail before any benchmark adapter work is attempted.
        """
        if benchmark_id == "terminal_bench_2_1":
            return [
                "genesis/terminal_bench_evidence.py",
                "genesis/benchmark_execution.py",
                "tests/test_terminal_bench_evidence.py",
                "tests/test_benchmark_execution.py",
                "genesis/benchmark_evidence.py",
                "genesis/competitive_benchmarks.py",
                "genesis/evaluation.py",
                "tests/test_benchmark_evidence.py",
                "tests/test_competitive_benchmarks.py",
            ]
        return [
            "genesis/benchmark_execution.py",
            "genesis/benchmark_evidence.py",
            "tests/test_benchmark_execution.py",
            "genesis/competitive_benchmarks.py",
            "genesis/evaluation.py",
            "tests/test_benchmark_evidence.py",
            "tests/test_competitive_benchmarks.py",
        ]

    def _runner_task(self, task: GenesisTask, benchmark_id: str) -> dict[str, Any]:
        context = self._runner_context(benchmark_id)
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

        readiness = self._execution_readiness(benchmark_id)
        if latest is not None and self._runner_generation(latest) >= self.MAX_RUNNER_INTEGRATION_GENERATIONS:
            if benchmark_id not in self.EVIDENCE_ADAPTER_BENCHMARKS:
                return {
                    "status": "runner_integration_exhausted",
                    "benchmark_id": benchmark_id,
                    "reason": (
                        "bounded runner-integration work is exhausted and no benchmark-specific evidence adapter is active"
                    ),
                    "missing": readiness["missing"],
                    "readiness": readiness,
                    "last_runner_task_id": latest.task_id,
                    "last_work_generation": self._runner_generation(latest),
                    "engineering_assistance_required": True,
                    "owner_action_required": False,
                }
            if not readiness["ready"]:
                return {
                    "status": "external_execution_required",
                    "benchmark_id": benchmark_id,
                    "reason": (
                        "bounded runner-integration work is exhausted; real benchmark execution prerequisites are missing"
                    ),
                    "missing": readiness["missing"],
                    "readiness": readiness,
                    "last_runner_task_id": latest.task_id,
                    "last_work_generation": self._runner_generation(latest),
                    "owner_action_required": True,
                }

        generation = self._runner_generation(latest) + 1 if latest is not None else 1
        prior_failure = ""
        if latest is not None:
            prior_failure = str(latest.last_error or "").strip()
            if not prior_failure and latest.failure_history:
                prior_failure = str(latest.failure_history[-1].get("error") or "").strip()
        objective = f"Make benchmark {benchmark_id} executable for Genesis using the official/comparable benchmark runner and pinned dataset. Produce real raw benchmark output with provenance; never invent, estimate, hard-code or self-award a score. Integrate the smallest reproducible runner/adapter needed so BenchmarkExecutionPlanner can stage independently validated evidence. Do not embed provider credentials or lock Genesis identity to a model/provider."
        if generation > 1:
            objective += (
                f" This is integration generation {generation}. Do not repeat the previous implementation approach; "
                "use different repository evidence, adapter boundaries, or execution strategy while preserving all validation rules."
            )
            if prior_failure:
                objective += f" Previous bounded attempt ended with: {prior_failure[:500]}"
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
                "strategy_change_required": generation > 1,
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
        if benchmark_id == "agents_last_exam":
            if input_path.is_file():
                job = json.loads(input_path.read_text(encoding="utf-8"))
                staged = AgentsLastExamEvidenceAdapter(self.root).stage(job)
                return {"status": "evidence_staged", "benchmark_id": benchmark_id, "candidate_path": str(staged)}
            return {
                "status": "external_execution_required",
                "benchmark_id": benchmark_id,
                "reason": "deterministic ALE evidence adapter is ready; a complete official pinned ALE run is still required",
                "missing": ["official_ale_full_experiment_result"],
                "readiness": AgentsLastExamEvidenceAdapter.execution_readiness(),
                "engineering_assistance_required": True,
                "owner_action_required": False,
            }
        if benchmark_id == "terminal_bench_2_1" and input_path.is_file():
            job = json.loads(input_path.read_text(encoding="utf-8"))
            staged = TerminalBench21EvidenceAdapter(self.root).stage(job)
            return {"status": "evidence_staged", "benchmark_id": benchmark_id, "candidate_path": str(staged)}

        return self._runner_task(task, benchmark_id)
