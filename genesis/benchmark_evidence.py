from __future__ import annotations

from datetime import datetime
import hashlib
import json
from pathlib import Path
from typing import Any


class BenchmarkEvidenceError(ValueError):
    pass


class CompetitiveBenchmarkEvidenceStore:
    """Validate and stage externally produced competitive benchmark evidence.

    Staged evidence is deliberately *not* written to
    ``runtime/competitive_benchmark_results.json`` and therefore cannot change
    the AI capability score. Independent validators must review and promote a
    staged candidate before the existing score pipeline can consume it.
    """

    def __init__(self, root: Path) -> None:
        self.root = Path(root).resolve()
        self.reference_path = self.root / "config" / "competitive_ai_reference.json"
        self.candidate_dir = self.root / "runtime" / "competitive_benchmark_candidates"

    def _reference(self) -> dict[str, dict[str, Any]]:
        data = json.loads(self.reference_path.read_text(encoding="utf-8"))
        return {str(item["id"]): item for item in data.get("benchmarks", [])}

    @staticmethod
    def _require_text(container: dict[str, Any], key: str) -> str:
        value = str(container.get(key, "")).strip()
        if not value:
            raise BenchmarkEvidenceError(f"{key} is required")
        return value

    @staticmethod
    def _require_iso8601(value: str) -> None:
        try:
            datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise BenchmarkEvidenceError("measured_at must be ISO-8601") from exc

    def validate(self, evidence: dict[str, Any]) -> dict[str, Any]:
        benchmark_id = self._require_text(evidence, "benchmark_id")
        reference = self._reference().get(benchmark_id)
        if reference is None:
            raise BenchmarkEvidenceError(f"unknown benchmark_id: {benchmark_id}")

        score = evidence.get("score")
        if isinstance(score, bool) or not isinstance(score, (int, float)):
            raise BenchmarkEvidenceError("score must be numeric")
        score = float(score)
        if not 0.0 <= score <= 100.0:
            raise BenchmarkEvidenceError("score must be between 0 and 100")

        unit = self._require_text(evidence, "unit")
        if unit != str(reference.get("unit", "score")):
            raise BenchmarkEvidenceError("unit does not match benchmark reference")

        provenance = evidence.get("provenance")
        if not isinstance(provenance, dict):
            raise BenchmarkEvidenceError("provenance object is required")
        source = self._require_text(provenance, "source")
        measured_at = self._require_text(provenance, "measured_at")
        self._require_iso8601(measured_at)

        runner = evidence.get("runner")
        if not isinstance(runner, dict):
            raise BenchmarkEvidenceError("runner object is required")
        runner_name = self._require_text(runner, "name")
        runner_version = self._require_text(runner, "version")
        config = self._require_text(runner, "config")
        dataset = self._require_text(runner, "dataset")

        raw_result = evidence.get("raw_result")
        if raw_result is None:
            raise BenchmarkEvidenceError("raw_result is required")
        raw_result_hash = hashlib.sha256(
            json.dumps(raw_result, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        ).hexdigest()

        return {
            "benchmark_id": benchmark_id,
            "family": str(reference.get("family", benchmark_id)),
            "score": score,
            "unit": unit,
            "status": "candidate",
            "provenance": {"source": source, "measured_at": measured_at},
            "runner": {
                "name": runner_name,
                "version": runner_version,
                "config": config,
                "dataset": dataset,
            },
            "raw_result": raw_result,
            "raw_result_sha256": raw_result_hash,
            "requires_independent_validation": True,
        }

    def stage(self, evidence: dict[str, Any]) -> Path:
        candidate = self.validate(evidence)
        self.candidate_dir.mkdir(parents=True, exist_ok=True)
        path = self.candidate_dir / f"{candidate['benchmark_id']}.json"
        path.write_text(json.dumps(candidate, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return path
