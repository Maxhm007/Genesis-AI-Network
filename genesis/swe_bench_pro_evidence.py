from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from .benchmark_evidence import BenchmarkEvidenceError, CompetitiveBenchmarkEvidenceStore


SWE_BENCH_PRO_DATASET = "ScaleAI/SWE-bench_Pro"
SWE_BENCH_PRO_REVISION = "a3fe51450709732f5d99ceb2b9de5adcc8d80b7e"
SWE_BENCH_PRO_TASK_COUNT = 731
SWE_BENCH_PRO_EVALUATOR = "https://github.com/scaleapi/SWE-bench_Pro-os/blob/main/swe_bench_pro_eval.py"
BASELINE_MODE = "bootstrap_only_no_patch"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class SWEBenchProEvidenceAdapter:
    """Stage a conservative SWE-bench Pro baseline from Genesis' real provider state.

    This adapter never accepts a caller-supplied score. The baseline is valid only
    when Genesis has no available non-bootstrap coding provider and therefore emits
    no patch for every pinned public SWE-bench Pro task. Under the official evaluator,
    an empty patch cannot resolve a task, so the derived score is exactly zero.

    This is a baseline for *providerless Genesis coding mode*, not a claim about a
    future Genesis model or any external model. Any available non-bootstrap provider
    must be measured with an actual patch-generating benchmark runner instead.
    """

    def __init__(self, root: Path) -> None:
        self.root = Path(root).resolve()
        self.store = CompetitiveBenchmarkEvidenceStore(self.root)

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

    @staticmethod
    def _canonical_hash(value: object) -> str:
        return hashlib.sha256(
            json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        ).hexdigest()

    @classmethod
    def dataset_identity(cls, row: dict[str, Any]) -> dict[str, str]:
        instance_id = str(row.get("instance_id") or "").strip()
        if not instance_id:
            raise BenchmarkEvidenceError("dataset record instance_id is required")
        problem = str(row.get("problem_statement") or "")
        return {
            "instance_id": instance_id,
            "repo": str(row.get("repo") or "").strip(),
            "base_commit": str(row.get("base_commit") or "").strip(),
            "dockerhub_tag": str(row.get("dockerhub_tag") or "").strip(),
            "problem_statement_sha256": hashlib.sha256(problem.encode("utf-8")).hexdigest(),
        }

    @classmethod
    def dataset_record_sha256(cls, row: dict[str, Any]) -> str:
        return cls._canonical_hash(cls.dataset_identity(row))

    def build_evidence(self, job: dict[str, Any]) -> dict[str, Any]:
        if self._required_text(job, "dataset") != SWE_BENCH_PRO_DATASET:
            raise BenchmarkEvidenceError("dataset must match pinned SWE-bench Pro dataset")
        if self._required_text(job, "revision") != SWE_BENCH_PRO_REVISION:
            raise BenchmarkEvidenceError("revision must match pinned SWE-bench Pro revision")
        if self._required_text(job, "mode") != BASELINE_MODE:
            raise BenchmarkEvidenceError("unsupported SWE-bench Pro baseline mode")

        measured_at = self._required_text(job, "measured_at")
        self._validate_timestamp(measured_at)
        source_url = self._required_text(job, "source_url")
        if not source_url.startswith("https://"):
            raise BenchmarkEvidenceError("source_url must be HTTPS")

        providers = job.get("available_providers")
        if not isinstance(providers, list) or not providers:
            raise BenchmarkEvidenceError("available_providers must record the measured provider state")
        normalized_providers = sorted({str(value).strip() for value in providers if str(value).strip()})
        if normalized_providers != ["genesis-bootstrap"]:
            raise BenchmarkEvidenceError(
                "providerless baseline requires genesis-bootstrap to be the only available provider"
            )

        results = job.get("results")
        if not isinstance(results, list) or len(results) != SWE_BENCH_PRO_TASK_COUNT:
            raise BenchmarkEvidenceError(
                f"SWE-bench Pro baseline requires exactly {SWE_BENCH_PRO_TASK_COUNT} task records"
            )

        seen: set[str] = set()
        normalized_results: list[dict[str, Any]] = []
        for item in results:
            if not isinstance(item, dict):
                raise BenchmarkEvidenceError("each SWE-bench Pro task record must be an object")
            identity = item.get("dataset_identity")
            if not isinstance(identity, dict):
                raise BenchmarkEvidenceError("each SWE-bench Pro task record requires dataset_identity")
            normalized_identity = {
                "instance_id": self._required_text(identity, "instance_id"),
                "repo": str(identity.get("repo") or "").strip(),
                "base_commit": str(identity.get("base_commit") or "").strip(),
                "dockerhub_tag": str(identity.get("dockerhub_tag") or "").strip(),
                "problem_statement_sha256": self._required_text(identity, "problem_statement_sha256").lower(),
            }
            if not _SHA256_RE.fullmatch(normalized_identity["problem_statement_sha256"]):
                raise BenchmarkEvidenceError("problem_statement_sha256 must be lowercase SHA-256")
            instance_id = normalized_identity["instance_id"]
            if instance_id in seen:
                raise BenchmarkEvidenceError(f"duplicate SWE-bench Pro instance_id: {instance_id}")
            seen.add(instance_id)
            if str(item.get("instance_id") or "").strip() != instance_id:
                raise BenchmarkEvidenceError("task instance_id must match dataset_identity")
            if str(item.get("patch", "")) != "":
                raise BenchmarkEvidenceError("providerless baseline task patches must be empty")
            if self._required_text(item, "outcome") != "no_patch":
                raise BenchmarkEvidenceError("providerless baseline outcomes must be no_patch")
            record_sha256 = self._required_text(item, "record_sha256").lower()
            if record_sha256 != self._canonical_hash(normalized_identity):
                raise BenchmarkEvidenceError("record_sha256 does not match dataset_identity")
            normalized_results.append(
                {
                    "instance_id": instance_id,
                    "patch": "",
                    "outcome": "no_patch",
                    "dataset_identity": normalized_identity,
                    "record_sha256": record_sha256,
                }
            )

        if len(seen) != SWE_BENCH_PRO_TASK_COUNT:
            raise BenchmarkEvidenceError("SWE-bench Pro instance ids must be unique")

        task_set_sha256 = self._canonical_hash(sorted(normalized_results, key=lambda row: row["instance_id"]))
        supplied_task_set_hash = self._required_text(job, "task_set_sha256").lower()
        if supplied_task_set_hash != task_set_sha256:
            raise BenchmarkEvidenceError("task_set_sha256 does not match the pinned enumerated task records")

        raw_result = dict(job)
        raw_result["available_providers"] = normalized_providers
        raw_result["results"] = normalized_results
        raw_result["task_set_sha256"] = task_set_sha256

        return {
            "benchmark_id": "swe_bench_pro",
            "score": 0.0,
            "unit": "percent",
            "provenance": {
                "source": source_url,
                "measured_at": measured_at,
            },
            "runner": {
                "name": "genesis-swe-bench-pro-providerless-baseline",
                "version": "1",
                "config": (
                    f"mode={BASELINE_MODE};provider=genesis-bootstrap;"
                    f"evaluator={SWE_BENCH_PRO_EVALUATOR}"
                ),
                "dataset": f"{SWE_BENCH_PRO_DATASET}@{SWE_BENCH_PRO_REVISION}",
            },
            "raw_result": raw_result,
        }

    def stage(self, job: dict[str, Any]) -> Path:
        return self.store.stage(self.build_evidence(job))

    def validate_staged_candidate(self, candidate: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(candidate, dict):
            raise BenchmarkEvidenceError("candidate must be an object")
        raw = candidate.get("raw_result")
        if not isinstance(raw, dict):
            raise BenchmarkEvidenceError("candidate raw_result must be an object")
        rebuilt = self.store.validate(self.build_evidence(raw))
        if candidate != rebuilt:
            raise BenchmarkEvidenceError("staged SWE-bench Pro candidate does not match independently rebuilt evidence")
        return rebuilt

    def verify_against_dataset(self, candidate: dict[str, Any], rows: Iterable[dict[str, Any]]) -> None:
        validated = self.validate_staged_candidate(candidate)
        raw = dict(validated["raw_result"])
        candidate_results = {
            str(item["instance_id"]): item
            for item in raw.get("results", [])
            if isinstance(item, dict) and str(item.get("instance_id") or "").strip()
        }
        source_rows = list(rows)
        if len(source_rows) != SWE_BENCH_PRO_TASK_COUNT:
            raise BenchmarkEvidenceError(
                f"pinned source dataset must contain exactly {SWE_BENCH_PRO_TASK_COUNT} records"
            )
        if len(candidate_results) != SWE_BENCH_PRO_TASK_COUNT:
            raise BenchmarkEvidenceError("candidate task count does not match source dataset")
        for row in source_rows:
            identity = self.dataset_identity(row)
            instance_id = identity["instance_id"]
            candidate_row = candidate_results.get(instance_id)
            if candidate_row is None:
                raise BenchmarkEvidenceError(f"candidate missing pinned dataset task {instance_id}")
            if candidate_row.get("dataset_identity") != identity:
                raise BenchmarkEvidenceError(f"candidate dataset identity mismatch for {instance_id}")
            if candidate_row.get("record_sha256") != self._canonical_hash(identity):
                raise BenchmarkEvidenceError(f"candidate dataset hash mismatch for {instance_id}")
