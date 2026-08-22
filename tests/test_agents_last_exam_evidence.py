from __future__ import annotations

import json
from pathlib import Path

import pytest

from genesis.agents_last_exam_evidence import (
    ALE_COMMIT,
    ALE_REPO,
    ALE_TASK_COUNT,
    ALE_TASK_LIST,
    ALE_TASK_LIST_BLOB_SHA,
    ALE_VERSION,
    AgentsLastExamEvidenceAdapter,
)
from genesis.benchmark_evidence import BenchmarkEvidenceError
from genesis.benchmark_execution import BenchmarkExecutionPlanner
from genesis.modules.task_queue import PersistentTaskQueue


def complete_job(score: float = 1.0) -> dict:
    return {
        "framework_repo": ALE_REPO,
        "framework_commit": ALE_COMMIT,
        "framework_version": ALE_VERSION,
        "task_list": ALE_TASK_LIST,
        "task_list_blob_sha": ALE_TASK_LIST_BLOB_SHA,
        "source_url": "https://example.invalid/ale/run-1",
        "measured_at": "2026-08-23T00:00:00Z",
        "agent": "genesis",
        "model": "provider-neutral",
        "environment": "official-ale-sandbox",
        "aggregate_score": 0.0,
        "results": [
            {"task_id": f"task/{index:03d}", "status": "completed", "score": score}
            for index in range(ALE_TASK_COUNT)
        ],
    }


def write_reference(root: Path) -> None:
    config = root / "config"
    config.mkdir(parents=True, exist_ok=True)
    (config / "competitive_ai_reference.json").write_text(
        json.dumps({"benchmarks": [{"id": "agents_last_exam", "family": "professional_agentic_work", "unit": "percent"}]}),
        encoding="utf-8",
    )


def test_adapter_derives_score_and_stages_candidate(tmp_path: Path) -> None:
    write_reference(tmp_path)
    job = complete_job(1.0)
    evidence = AgentsLastExamEvidenceAdapter(tmp_path).build_evidence(job)
    assert evidence["score"] == 100.0
    assert evidence["raw_result"]["aggregate_score"] == 0.0
    staged = AgentsLastExamEvidenceAdapter(tmp_path).stage(job)
    payload = json.loads(staged.read_text(encoding="utf-8"))
    assert payload["status"] == "candidate"
    assert payload["requires_independent_validation"] is True


def test_adapter_rejects_incomplete_wrong_revision_and_nonzero_timeout(tmp_path: Path) -> None:
    write_reference(tmp_path)
    adapter = AgentsLastExamEvidenceAdapter(tmp_path)
    missing = complete_job()
    missing["results"].pop()
    with pytest.raises(BenchmarkEvidenceError):
        adapter.build_evidence(missing)
    wrong = complete_job()
    wrong["framework_commit"] = "wrong"
    with pytest.raises(BenchmarkEvidenceError):
        adapter.build_evidence(wrong)
    timeout = complete_job()
    timeout["results"][0]["status"] = "timeout"
    with pytest.raises(BenchmarkEvidenceError):
        adapter.build_evidence(timeout)


def test_planner_stages_real_ale_input(tmp_path: Path) -> None:
    write_reference(tmp_path)
    queue = PersistentTaskQueue(tmp_path / "runtime" / "genesis_tasks.sqlite3")
    task = queue.create(
        "Measure ALE",
        module_id="genesis.evaluation",
        priority=92,
        payload={"task_type": "frontier_benchmark_measurement", "benchmark": {"benchmark_id": "agents_last_exam"}},
    )
    input_dir = tmp_path / "runtime" / "competitive_benchmark_inputs"
    input_dir.mkdir(parents=True, exist_ok=True)
    (input_dir / "agents_last_exam.json").write_text(json.dumps(complete_job(0.5)), encoding="utf-8")
    result = BenchmarkExecutionPlanner(tmp_path).advance(task)
    assert result["status"] == "evidence_staged"
    candidate = json.loads(Path(result["candidate_path"]).read_text(encoding="utf-8"))
    assert candidate["score"] == 50.0
