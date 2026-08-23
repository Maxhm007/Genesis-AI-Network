from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DURABLE_RESULTS_PATH = Path("evidence/validated_benchmark_results.json")
RUNTIME_RESULTS_PATH = Path("runtime/competitive_benchmark_results.json")


def _load(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {"benchmarks": {}}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"benchmarks": {}}
    if not isinstance(value, dict):
        return {"benchmarks": {}}
    benchmarks = value.get("benchmarks")
    if not isinstance(benchmarks, dict):
        value["benchmarks"] = {}
    return value


def _parse_time(value: object) -> datetime:
    text = str(value or "").strip()
    if not text:
        return datetime.min.replace(tzinfo=timezone.utc)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return datetime.min.replace(tzinfo=timezone.utc)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _measurement_time(result: object) -> datetime:
    if not isinstance(result, dict):
        return datetime.min.replace(tzinfo=timezone.utc)
    provenance = result.get("provenance")
    measured_at = provenance.get("measured_at") if isinstance(provenance, dict) else None
    return max(_parse_time(measured_at), _parse_time(result.get("validated_at")))


def _validated(result: object) -> bool:
    if not isinstance(result, dict):
        return False
    if str(result.get("status") or "").lower() != "validated":
        return False
    if "score" not in result:
        return False
    provenance = result.get("provenance")
    if not isinstance(provenance, dict):
        return False
    if not str(provenance.get("source") or "").strip():
        return False
    if not str(provenance.get("measured_at") or "").strip():
        return False
    return True


def _merge_payloads(*payloads: dict[str, Any]) -> dict[str, Any]:
    merged: dict[str, Any] = {"benchmarks": {}}
    for payload in payloads:
        benchmarks = payload.get("benchmarks")
        if not isinstance(benchmarks, dict):
            continue
        for benchmark_id, result in benchmarks.items():
            if not _validated(result):
                continue
            current = merged["benchmarks"].get(str(benchmark_id))
            if current is None or _measurement_time(result) >= _measurement_time(current):
                merged["benchmarks"][str(benchmark_id)] = result
    newest = datetime.min.replace(tzinfo=timezone.utc)
    for result in merged["benchmarks"].values():
        newest = max(newest, _measurement_time(result))
    if newest > datetime.min.replace(tzinfo=timezone.utc):
        merged["updated_at"] = newest.isoformat()
    return merged


def hydrate_validated_benchmark_state(root: Path) -> dict[str, Any]:
    """Merge durable validated evidence into volatile runtime state.

    Runtime caches are allowed to disappear or be restored out of order. The
    repository-backed evidence snapshot is the correctness anchor. If runtime
    contains a newer independently validated measurement it wins for that
    benchmark; otherwise durable evidence is restored into runtime.
    """

    root = Path(root).resolve()
    durable = _load(root / DURABLE_RESULTS_PATH)
    runtime_path = root / RUNTIME_RESULTS_PATH
    runtime = _load(runtime_path)
    merged = _merge_payloads(durable, runtime)
    if merged.get("benchmarks"):
        runtime_path.parent.mkdir(parents=True, exist_ok=True)
        runtime_path.write_text(json.dumps(merged, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return merged


def persist_validated_benchmark_snapshot(root: Path, source_path: Path) -> dict[str, Any]:
    """Persist only quorum-validated benchmark summaries from an artifact.

    The raw benchmark artifact remains in Actions for audit. The tracked snapshot
    contains the minimum fields needed to make validated measurement state durable
    across runners and cache loss.
    """

    root = Path(root).resolve()
    source = _load(Path(source_path))
    durable_path = root / DURABLE_RESULTS_PATH
    durable = _load(durable_path)
    accepted: dict[str, Any] = {"benchmarks": {}}

    for benchmark_id, result in source.get("benchmarks", {}).items():
        if not _validated(result):
            continue
        validators = result.get("validated_by")
        if not isinstance(validators, list) or len({str(v).strip() for v in validators if str(v).strip()}) < 2:
            continue
        if result.get("requires_independent_validation") not in {False, None}:
            continue
        if not str(result.get("candidate_sha256") or "").strip():
            continue
        if not str(result.get("raw_result_sha256") or "").strip():
            continue
        summary = {
            key: result[key]
            for key in (
                "benchmark_id",
                "family",
                "score",
                "status",
                "provenance",
                "raw_result_sha256",
                "candidate_sha256",
                "validated_at",
                "validated_by",
                "requires_independent_validation",
            )
            if key in result
        }
        accepted["benchmarks"][str(benchmark_id)] = summary

    if not accepted["benchmarks"]:
        raise ValueError("no independently validated benchmark result found in snapshot")

    merged = _merge_payloads(durable, accepted)
    durable_path.parent.mkdir(parents=True, exist_ok=True)
    durable_path.write_text(json.dumps(merged, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    hydrate_validated_benchmark_state(root)
    return merged
