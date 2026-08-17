from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from .benchmark_evidence import BenchmarkEvidenceError, CompetitiveBenchmarkEvidenceStore


TERMINAL_BENCH_2_1_DATASET = "terminal-bench/terminal-bench-2-1"
TERMINAL_BENCH_2_1_TASK_COUNT = 89
MIN_TRIALS_PER_TASK = 5


class TerminalBench21EvidenceAdapter:
    """Convert a complete Harbor Terminal-Bench 2.1 job into staged evidence.

    The adapter derives the score from per-trial rewards; callers cannot supply
    an arbitrary benchmark score. It also requires the complete pinned 2.1
    dataset and at least five trials for every task before staging a candidate.
    The resulting candidate still requires independent Genesis validation and
    therefore cannot affect the capability score directly.
    """

    def __init__(self, root: Path) -> None:
        self.store = CompetitiveBenchmarkEvidenceStore(root)

    @staticmethod
    def _required_text(container: dict[str, Any], key: str) -> str:
        value = str(container.get(key, "")).strip()
        if not value:
            raise BenchmarkEvidenceError(f"{key} is required")
        return value

    @staticmethod
    def _validate_timestamp(value: str) -> None:
        try:
            datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise BenchmarkEvidenceError("measured_at must be ISO-8601") from exc

    def build_evidence(self, job: dict[str, Any]) -> dict[str, Any]:
        dataset = self._required_text(job, "dataset")
        if dataset != TERMINAL_BENCH_2_1_DATASET:
            raise BenchmarkEvidenceError("dataset must be the pinned Terminal-Bench 2.1 dataset")

        job_url = self._required_text(job, "job_url")
        if not job_url.startswith("https://hub.harborframework.com/jobs/"):
            raise BenchmarkEvidenceError("job_url must reference a Harbor Hub job")

        measured_at = self._required_text(job, "measured_at")
        self._validate_timestamp(measured_at)
        harbor_version = self._required_text(job, "harbor_version")
        agent = self._required_text(job, "agent")
        model = self._required_text(job, "model")
        sandbox = self._required_text(job, "sandbox")

        trials = job.get("trials")
        if not isinstance(trials, dict):
            raise BenchmarkEvidenceError("trials must be an object keyed by task id")
        if len(trials) != TERMINAL_BENCH_2_1_TASK_COUNT:
            raise BenchmarkEvidenceError(
                f"Terminal-Bench 2.1 requires exactly {TERMINAL_BENCH_2_1_TASK_COUNT} tasks"
            )

        task_scores: list[float] = []
        for task_id, task_trials in sorted(trials.items()):
            if not str(task_id).strip():
                raise BenchmarkEvidenceError("task id cannot be empty")
            if not isinstance(task_trials, list) or len(task_trials) < MIN_TRIALS_PER_TASK:
                raise BenchmarkEvidenceError(
                    f"task {task_id} requires at least {MIN_TRIALS_PER_TASK} trials"
                )
            rewards: list[float] = []
            for trial in task_trials:
                if not isinstance(trial, dict):
                    raise BenchmarkEvidenceError(f"task {task_id} trial must be an object")
                reward = trial.get("reward")
                if isinstance(reward, bool) or not isinstance(reward, (int, float)):
                    raise BenchmarkEvidenceError(f"task {task_id} reward must be numeric")
                reward = float(reward)
                if not 0.0 <= reward <= 1.0:
                    raise BenchmarkEvidenceError(f"task {task_id} reward must be between 0 and 1")
                rewards.append(reward)
            task_scores.append(sum(rewards) / len(rewards))

        score = 100.0 * sum(task_scores) / len(task_scores)
        return {
            "benchmark_id": "terminal_bench_2_1",
            "score": score,
            "unit": "percent",
            "provenance": {
                "source": job_url,
                "measured_at": measured_at,
            },
            "runner": {
                "name": "harbor",
                "version": harbor_version,
                "config": f"agent={agent};model={model};sandbox={sandbox};trials>={MIN_TRIALS_PER_TASK}",
                "dataset": dataset,
            },
            "raw_result": job,
        }

    def stage(self, job: dict[str, Any]) -> Path:
        return self.store.stage(self.build_evidence(job))
