from __future__ import annotations

import json
from pathlib import Path

import pytest

from genesis.benchmark_evidence import BenchmarkEvidenceError, CompetitiveBenchmarkEvidenceStore


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


def valid_evidence() -> dict:
    return {
        "benchmark_id": "terminal_bench_2_1",
        "score": 42.0,
        "unit": "percent",
        "provenance": {
            "source": "terminal-bench official runner output",
            "measured_at": "2026-08-17T12:00:00Z",
        },
        "runner": {
            "name": "terminal-bench",
            "version": "2.1",
            "config": "official/default",
            "dataset": "terminal-bench-2.1",
        },
        "raw_result": {"passed": 42, "total": 100},
    }


def test_stage_preserves_candidate_boundary(tmp_path: Path) -> None:
    write_reference(tmp_path)
    store = CompetitiveBenchmarkEvidenceStore(tmp_path)
    path = store.stage(valid_evidence())
    staged = json.loads(path.read_text(encoding="utf-8"))
    assert staged["status"] == "candidate"
    assert staged["requires_independent_validation"] is True
    assert staged["score"] == 42.0
    assert len(staged["raw_result_sha256"]) == 64
    assert not (tmp_path / "runtime" / "competitive_benchmark_results.json").exists()


def test_reference_score_alone_cannot_be_staged_as_measurement(tmp_path: Path) -> None:
    write_reference(tmp_path)
    store = CompetitiveBenchmarkEvidenceStore(tmp_path)
    with pytest.raises(BenchmarkEvidenceError, match="provenance object is required"):
        store.stage({
            "benchmark_id": "terminal_bench_2_1",
            "score": 91.9,
            "unit": "percent",
        })


def test_runner_and_unit_must_match_real_evidence(tmp_path: Path) -> None:
    write_reference(tmp_path)
    store = CompetitiveBenchmarkEvidenceStore(tmp_path)
    evidence = valid_evidence()
    evidence["unit"] = "index"
    with pytest.raises(BenchmarkEvidenceError, match="unit does not match"):
        store.stage(evidence)

    evidence = valid_evidence()
    evidence["runner"] = {}
    with pytest.raises(BenchmarkEvidenceError, match="name is required"):
        store.stage(evidence)
