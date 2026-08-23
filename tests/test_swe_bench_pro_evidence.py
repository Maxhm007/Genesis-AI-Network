from __future__ import annotations

import hashlib
import json

import pytest

from genesis.benchmark_evidence import BenchmarkEvidenceError
from genesis.swe_bench_pro_evidence import (
    BASELINE_MODE,
    SWE_BENCH_PRO_DATASET,
    SWE_BENCH_PRO_REVISION,
    SWE_BENCH_PRO_TASK_COUNT,
    SWEBenchProEvidenceAdapter,
)


def write_reference(root) -> None:
    config = root / "config"
    config.mkdir(parents=True)
    (config / "competitive_ai_reference.json").write_text(
        json.dumps(
            {
                "benchmarks": [
                    {
                        "id": "swe_bench_pro",
                        "family": "software_engineering",
                        "reference_score": 80.3,
                        "unit": "percent",
                        "weight": 10,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )


def make_job(root) -> dict:
    adapter = SWEBenchProEvidenceAdapter(root)
    results = []
    for index in range(SWE_BENCH_PRO_TASK_COUNT):
        identity = {
            "instance_id": f"instance-{index:04d}",
            "repo": "example/repo",
            "base_commit": f"commit-{index}",
            "dockerhub_tag": f"tag-{index}",
            "problem_statement_sha256": hashlib.sha256(f"problem-{index}".encode()).hexdigest(),
        }
        results.append(
            {
                "instance_id": identity["instance_id"],
                "patch": "",
                "outcome": "no_patch",
                "dataset_identity": identity,
                "record_sha256": adapter._canonical_hash(identity),
            }
        )
    results.sort(key=lambda row: row["instance_id"])
    return {
        "dataset": SWE_BENCH_PRO_DATASET,
        "revision": SWE_BENCH_PRO_REVISION,
        "mode": BASELINE_MODE,
        "measured_at": "2026-08-23T16:00:00Z",
        "source_url": "https://huggingface.co/datasets/ScaleAI/SWE-bench_Pro",
        "available_providers": ["genesis-bootstrap"],
        "task_set_sha256": adapter._canonical_hash(results),
        "results": results,
    }


def test_providerless_baseline_derives_zero_and_stages(tmp_path) -> None:
    write_reference(tmp_path)
    adapter = SWEBenchProEvidenceAdapter(tmp_path)
    candidate_path = adapter.stage(make_job(tmp_path))
    candidate = json.loads(candidate_path.read_text(encoding="utf-8"))
    assert candidate["benchmark_id"] == "swe_bench_pro"
    assert candidate["score"] == 0.0
    assert candidate["status"] == "candidate"
    assert candidate["requires_independent_validation"] is True
    assert len(candidate["raw_result"]["results"]) == SWE_BENCH_PRO_TASK_COUNT
    assert adapter.validate_staged_candidate(candidate) == candidate


def test_providerless_baseline_rejects_non_bootstrap_provider(tmp_path) -> None:
    write_reference(tmp_path)
    adapter = SWEBenchProEvidenceAdapter(tmp_path)
    job = make_job(tmp_path)
    job["available_providers"] = ["genesis-bootstrap", "genesis-local-model"]
    with pytest.raises(BenchmarkEvidenceError, match="only available provider"):
        adapter.stage(job)


def test_providerless_baseline_rejects_patch_or_tampered_dataset_identity(tmp_path) -> None:
    write_reference(tmp_path)
    adapter = SWEBenchProEvidenceAdapter(tmp_path)
    job = make_job(tmp_path)
    job["results"][0]["patch"] = "diff --git a/x b/x"
    with pytest.raises(BenchmarkEvidenceError, match="patches must be empty"):
        adapter.stage(job)

    job = make_job(tmp_path)
    job["results"][0]["dataset_identity"]["base_commit"] = "tampered"
    with pytest.raises(BenchmarkEvidenceError, match="record_sha256"):
        adapter.stage(job)
