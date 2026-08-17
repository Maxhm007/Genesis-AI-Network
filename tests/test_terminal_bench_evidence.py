from __future__ import annotations

import json
from pathlib import Path

import pytest

from genesis.benchmark_evidence import BenchmarkEvidenceError
from genesis.terminal_bench_evidence import (
    MIN_TRIALS_PER_TASK,
    TERMINAL_BENCH_2_1_DATASET,
    TERMINAL_BENCH_2_1_TASK_COUNT,
    TerminalBench21EvidenceAdapter,
)


def write_reference(root: Path) -> None:
    (root / "config").mkdir(parents=True)
    (root / "config" / "competitive_ai_reference.json").write_text(
        json.dumps({"benchmarks": [{
            "id": "terminal_bench_2_1",
            "family": "long_horizon_tool_coding",
            "reference_score": 91.9,
            "unit": "percent",
            "weight": 10,
        }]}),
        encoding="utf-8",
    )


def complete_job() -> dict:
    trials = {
        f"task-{index:03d}": [
            {"reward": 1.0 if (index + trial) % 2 == 0 else 0.0}
            for trial in range(MIN_TRIALS_PER_TASK)
        ]
        for index in range(TERMINAL_BENCH_2_1_TASK_COUNT)
    }
    return {
        "dataset": TERMINAL_BENCH_2_1_DATASET,
        "job_url": "https://hub.harborframework.com/jobs/example-job-id",
        "measured_at": "2026-08-17T13:00:00Z",
        "harbor_version": "0.1.0",
        "agent": "genesis",
        "model": "configured-provider",
        "sandbox": "docker",
        "trials": trials,
    }


def test_score_is_derived_from_complete_trial_evidence(tmp_path: Path) -> None:
    write_reference(tmp_path)
    adapter = TerminalBench21EvidenceAdapter(tmp_path)
    job = complete_job()
    evidence = adapter.build_evidence(job)

    per_task = [
        sum(trial["reward"] for trial in task_trials) / len(task_trials)
        for task_trials in job["trials"].values()
    ]
    expected = 100.0 * sum(per_task) / len(per_task)
    assert evidence["score"] == pytest.approx(expected)
    assert evidence["benchmark_id"] == "terminal_bench_2_1"
    assert evidence["provenance"]["source"] == job["job_url"]

    path = adapter.stage(job)
    staged = json.loads(path.read_text(encoding="utf-8"))
    assert staged["status"] == "candidate"
    assert staged["requires_independent_validation"] is True
    assert not (tmp_path / "runtime" / "competitive_benchmark_results.json").exists()


def test_partial_dataset_is_rejected(tmp_path: Path) -> None:
    write_reference(tmp_path)
    adapter = TerminalBench21EvidenceAdapter(tmp_path)
    job = complete_job()
    job["trials"].pop(next(iter(job["trials"])))
    with pytest.raises(BenchmarkEvidenceError, match="exactly 89 tasks"):
        adapter.stage(job)


def test_fewer_than_five_trials_is_rejected(tmp_path: Path) -> None:
    write_reference(tmp_path)
    adapter = TerminalBench21EvidenceAdapter(tmp_path)
    job = complete_job()
    first_task = next(iter(job["trials"]))
    job["trials"][first_task] = job["trials"][first_task][:4]
    with pytest.raises(BenchmarkEvidenceError, match="at least 5 trials"):
        adapter.stage(job)


def test_non_harbor_source_is_rejected(tmp_path: Path) -> None:
    write_reference(tmp_path)
    adapter = TerminalBench21EvidenceAdapter(tmp_path)
    job = complete_job()
    job["job_url"] = "https://example.com/fake-result"
    with pytest.raises(BenchmarkEvidenceError, match="Harbor Hub job"):
        adapter.stage(job)
