from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .benchmark_evidence import BenchmarkEvidenceError
from .swe_bench_pro_evidence import SWEBenchProEvidenceAdapter


VALIDATED_RESULTS_FILE = "competitive_benchmark_results.json"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def file_sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _load_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception as exc:
        raise BenchmarkEvidenceError(f"invalid benchmark evidence JSON: {path}") from exc
    if not isinstance(value, dict):
        raise BenchmarkEvidenceError("benchmark evidence must be a JSON object")
    return value


def validate_candidate(root: Path, candidate_path: Path) -> dict[str, Any]:
    root = Path(root).resolve()
    candidate_path = Path(candidate_path)
    candidate = _load_object(candidate_path)
    benchmark_id = str(candidate.get("benchmark_id") or "").strip()
    if benchmark_id == "swe_bench_pro":
        return SWEBenchProEvidenceAdapter(root).validate_staged_candidate(candidate)
    raise BenchmarkEvidenceError(
        f"no independent benchmark-specific validator is registered for {benchmark_id or 'unknown'}"
    )


def create_vote(root: Path, candidate_path: Path, validator_id: str) -> dict[str, Any]:
    validator_id = validator_id.strip()
    if not validator_id:
        raise BenchmarkEvidenceError("validator_id is required")
    validated = validate_candidate(root, candidate_path)
    candidate_hash = file_sha256(candidate_path)
    validation_payload = {
        "benchmark_id": validated["benchmark_id"],
        "candidate_sha256": candidate_hash,
        "raw_result_sha256": validated["raw_result_sha256"],
        "validator_id": validator_id,
        "decision": "pass",
    }
    validation_digest = hashlib.sha256(
        json.dumps(validation_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return {
        **validation_payload,
        "validated_at": utc_now(),
        "validation_digest": validation_digest,
    }


def _validate_vote(vote: dict[str, Any], *, candidate_hash: str, benchmark_id: str, raw_hash: str) -> str:
    validator_id = str(vote.get("validator_id") or "").strip()
    if not validator_id:
        raise BenchmarkEvidenceError("benchmark validator vote is missing validator_id")
    if str(vote.get("decision") or "") != "pass":
        raise BenchmarkEvidenceError(f"benchmark validator {validator_id} did not pass candidate")
    if str(vote.get("candidate_sha256") or "") != candidate_hash:
        raise BenchmarkEvidenceError("benchmark validator vote candidate hash mismatch")
    if str(vote.get("benchmark_id") or "") != benchmark_id:
        raise BenchmarkEvidenceError("benchmark validator vote benchmark mismatch")
    if str(vote.get("raw_result_sha256") or "") != raw_hash:
        raise BenchmarkEvidenceError("benchmark validator vote raw-result hash mismatch")
    expected_payload = {
        "benchmark_id": benchmark_id,
        "candidate_sha256": candidate_hash,
        "raw_result_sha256": raw_hash,
        "validator_id": validator_id,
        "decision": "pass",
    }
    expected_digest = hashlib.sha256(
        json.dumps(expected_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    if str(vote.get("validation_digest") or "") != expected_digest:
        raise BenchmarkEvidenceError("benchmark validator vote digest mismatch")
    return validator_id


def promote_candidate(
    root: Path,
    candidate_path: Path,
    vote_paths: list[Path],
    *,
    minimum_validators: int = 2,
) -> dict[str, Any]:
    root = Path(root).resolve()
    validated = validate_candidate(root, candidate_path)
    candidate_hash = file_sha256(candidate_path)
    validator_ids: list[str] = []
    for vote_path in vote_paths:
        vote = _load_object(vote_path)
        validator_id = _validate_vote(
            vote,
            candidate_hash=candidate_hash,
            benchmark_id=str(validated["benchmark_id"]),
            raw_hash=str(validated["raw_result_sha256"]),
        )
        if validator_id in validator_ids:
            raise BenchmarkEvidenceError("benchmark evidence quorum requires distinct validator ids")
        validator_ids.append(validator_id)
    if len(validator_ids) < minimum_validators:
        raise BenchmarkEvidenceError(
            f"benchmark evidence promotion requires at least {minimum_validators} independent validators"
        )

    results_path = root / "runtime" / VALIDATED_RESULTS_FILE
    results_path.parent.mkdir(parents=True, exist_ok=True)
    if results_path.is_file():
        try:
            results = json.loads(results_path.read_text(encoding="utf-8"))
        except Exception:
            results = {}
    else:
        results = {}
    if not isinstance(results, dict):
        results = {}
    benchmarks = results.get("benchmarks")
    if not isinstance(benchmarks, dict):
        benchmarks = {}

    promoted = dict(validated)
    promoted["status"] = "validated"
    promoted["requires_independent_validation"] = False
    promoted["validated_at"] = utc_now()
    promoted["candidate_sha256"] = candidate_hash
    promoted["validated_by"] = sorted(validator_ids)
    benchmarks[str(validated["benchmark_id"])] = promoted
    results["benchmarks"] = benchmarks
    results["updated_at"] = promoted["validated_at"]
    results_path.write_text(json.dumps(results, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return promoted
