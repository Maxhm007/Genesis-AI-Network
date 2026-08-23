import json
from pathlib import Path

import pytest

from genesis.benchmark_state import (
    hydrate_validated_benchmark_state,
    persist_validated_benchmark_snapshot,
)


def _result(score: float, measured_at: str) -> dict:
    return {
        "benchmark_id": "swe_bench_pro",
        "family": "software_engineering",
        "score": score,
        "status": "validated",
        "provenance": {
            "source": "https://example.invalid/pinned-benchmark",
            "measured_at": measured_at,
        },
        "raw_result_sha256": "a" * 64,
        "candidate_sha256": "b" * 64,
        "validated_at": measured_at,
        "validated_by": ["validator-a", "validator-b"],
        "requires_independent_validation": False,
    }


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_durable_validated_result_recovers_over_stale_runtime(tmp_path: Path) -> None:
    durable = _result(0.0, "2026-08-23T17:07:50+00:00")
    stale = _result(5.0, "2026-08-22T17:07:50+00:00")
    _write(tmp_path / "evidence/validated_benchmark_results.json", {"benchmarks": {"swe_bench_pro": durable}})
    _write(tmp_path / "runtime/competitive_benchmark_results.json", {"benchmarks": {"swe_bench_pro": stale}})

    merged = hydrate_validated_benchmark_state(tmp_path)

    assert merged["benchmarks"]["swe_bench_pro"]["score"] == 0.0
    runtime = json.loads((tmp_path / "runtime/competitive_benchmark_results.json").read_text(encoding="utf-8"))
    assert runtime["benchmarks"]["swe_bench_pro"]["score"] == 0.0


def test_newer_validated_runtime_result_wins_over_durable_snapshot(tmp_path: Path) -> None:
    durable = _result(0.0, "2026-08-23T17:07:50+00:00")
    newer = _result(2.0, "2026-08-24T17:07:50+00:00")
    _write(tmp_path / "evidence/validated_benchmark_results.json", {"benchmarks": {"swe_bench_pro": durable}})
    _write(tmp_path / "runtime/competitive_benchmark_results.json", {"benchmarks": {"swe_bench_pro": newer}})

    merged = hydrate_validated_benchmark_state(tmp_path)

    assert merged["benchmarks"]["swe_bench_pro"]["score"] == 2.0


def test_persistence_requires_independent_validator_quorum(tmp_path: Path) -> None:
    invalid = _result(0.0, "2026-08-23T17:07:50+00:00")
    invalid["validated_by"] = ["validator-a"]
    source = tmp_path / "artifact/results.json"
    _write(source, {"benchmarks": {"swe_bench_pro": invalid}})

    with pytest.raises(ValueError, match="no independently validated benchmark result"):
        persist_validated_benchmark_snapshot(tmp_path, source)
