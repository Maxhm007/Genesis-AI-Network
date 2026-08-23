from __future__ import annotations

import hashlib
import json

import pytest

from genesis.benchmark_evidence import BenchmarkEvidenceError
from genesis.benchmark_evidence_validation import create_vote, promote_candidate
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


def stage_candidate(root):
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
    return adapter.stage(
        {
            "dataset": SWE_BENCH_PRO_DATASET,
            "revision": SWE_BENCH_PRO_REVISION,
            "mode": BASELINE_MODE,
            "measured_at": "2026-08-23T16:00:00Z",
            "source_url": "https://huggingface.co/datasets/ScaleAI/SWE-bench_Pro",
            "available_providers": ["genesis-bootstrap"],
            "task_set_sha256": adapter._canonical_hash(results),
            "results": results,
        }
    )


def test_two_distinct_votes_promote_validated_result(tmp_path) -> None:
    write_reference(tmp_path)
    candidate = stage_candidate(tmp_path)
    vote_a = tmp_path / "vote-a.json"
    vote_b = tmp_path / "vote-b.json"
    vote_a.write_text(json.dumps(create_vote(tmp_path, candidate, "validator-a")), encoding="utf-8")
    vote_b.write_text(json.dumps(create_vote(tmp_path, candidate, "validator-b")), encoding="utf-8")

    promoted = promote_candidate(tmp_path, candidate, [vote_a, vote_b])
    assert promoted["status"] == "validated"
    assert promoted["score"] == 0.0
    assert promoted["validated_by"] == ["validator-a", "validator-b"]

    results = json.loads(
        (tmp_path / "runtime" / "competitive_benchmark_results.json").read_text(encoding="utf-8")
    )
    assert results["benchmarks"]["swe_bench_pro"]["status"] == "validated"


def test_duplicate_validator_cannot_form_quorum(tmp_path) -> None:
    write_reference(tmp_path)
    candidate = stage_candidate(tmp_path)
    vote_a = tmp_path / "vote-a.json"
    vote_b = tmp_path / "vote-b.json"
    vote = create_vote(tmp_path, candidate, "validator-a")
    vote_a.write_text(json.dumps(vote), encoding="utf-8")
    vote_b.write_text(json.dumps(vote), encoding="utf-8")
    with pytest.raises(BenchmarkEvidenceError, match="distinct validator"):
        promote_candidate(tmp_path, candidate, [vote_a, vote_b])


def test_tampered_candidate_invalidates_existing_votes(tmp_path) -> None:
    write_reference(tmp_path)
    candidate = stage_candidate(tmp_path)
    vote_a = tmp_path / "vote-a.json"
    vote_b = tmp_path / "vote-b.json"
    vote_a.write_text(json.dumps(create_vote(tmp_path, candidate, "validator-a")), encoding="utf-8")
    vote_b.write_text(json.dumps(create_vote(tmp_path, candidate, "validator-b")), encoding="utf-8")
    payload = json.loads(candidate.read_text(encoding="utf-8"))
    payload["provenance"]["source"] = "https://example.invalid/tampered"
    candidate.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(BenchmarkEvidenceError):
        promote_candidate(tmp_path, candidate, [vote_a, vote_b])
