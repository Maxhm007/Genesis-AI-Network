from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from .benchmark_evidence import BenchmarkEvidenceError, CompetitiveBenchmarkEvidenceStore


ALE_REPO = 'https://github.com/rdi-berkeley/agents-last-exam'
ALE_COMMIT = '1c9cc7e6825c8123344b78245e0eaceebfa18fa7'
ALE_VERSION = '0.1.0'
ALE_TASK_LIST = 'selected_tasks/full.txt'
ALE_TASK_LIST_BLOB_SHA = 'd94c985483153a4dbd169fe63d9300b004fe96f0'
ALE_TASK_COUNT = 152


class AgentsLastExamEvidenceAdapter:
    """Convert a complete pinned ALE full-task run into staged evidence."""

    def __init__(self, root: Path) -> None:
        self.store = CompetitiveBenchmarkEvidenceStore(root)

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

    @classmethod
    def execution_readiness(cls) -> dict[str, Any]:
        return {
            "benchmark_id": "agents_last_exam",
            "framework_repo": ALE_REPO,
            "framework_commit": ALE_COMMIT,
            "framework_version": ALE_VERSION,
            "task_list": ALE_TASK_LIST,
            "task_list_blob_sha": ALE_TASK_LIST_BLOB_SHA,
            "task_count": ALE_TASK_COUNT,
            "runner": "uv run python -m ale_run run <experiment.yaml>",
            "provider_independent_adapter": True,
        }

    def build_evidence(self, job: dict[str, Any]) -> dict[str, Any]:
        if self._required_text(job, "framework_repo") != ALE_REPO:
            raise BenchmarkEvidenceError("framework_repo must be the official ALE repository")
        if self._required_text(job, "framework_commit") != ALE_COMMIT:
            raise BenchmarkEvidenceError("framework_commit must match the pinned ALE revision")
        if self._required_text(job, "framework_version") != ALE_VERSION:
            raise BenchmarkEvidenceError("framework_version must match the pinned ALE version")
        if self._required_text(job, "task_list") != ALE_TASK_LIST:
            raise BenchmarkEvidenceError("task_list must be the pinned ALE full task list")
        if self._required_text(job, "task_list_blob_sha") != ALE_TASK_LIST_BLOB_SHA:
            raise BenchmarkEvidenceError("task_list_blob_sha must match the pinned ALE task list")

        source_url = self._required_text(job, "source_url")
        if not source_url.startswith("https://"):
            raise BenchmarkEvidenceError("source_url must be an HTTPS provenance URL")
        measured_at = self._required_text(job, "measured_at")
        self._validate_timestamp(measured_at)
        agent = self._required_text(job, "agent")
        model = self._required_text(job, "model")
        environment = self._required_text(job, "environment")

        results = job.get("results")
        if not isinstance(results, list) or len(results) != ALE_TASK_COUNT:
            raise BenchmarkEvidenceError(
                f"Agents' Last Exam requires exactly {ALE_TASK_COUNT} pinned task results"
            )

        seen: set[str] = set()
        scores: list[float] = []
        for item in results:
            if not isinstance(item, dict):
                raise BenchmarkEvidenceError("each ALE result must be an object")
            task_id = self._required_text(item, "task_id")
            if task_id in seen:
                raise BenchmarkEvidenceError(f"duplicate ALE task id: {task_id}")
            seen.add(task_id)
            status = self._required_text(item, "status")
            if status not in {"completed", "timeout"}:
                raise BenchmarkEvidenceError(f"unsupported ALE task status: {status}")
            raw_score = item.get("score")
            if isinstance(raw_score, bool) or not isinstance(raw_score, (int, float)):
                raise BenchmarkEvidenceError(f"task {task_id} score must be numeric")
            score = float(raw_score)
            if not 0.0 <= score <= 1.0:
                raise BenchmarkEvidenceError(f"task {task_id} score must be between 0 and 1")
            if status == "timeout" and score != 0.0:
                raise BenchmarkEvidenceError("timeout ALE tasks must contribute score 0")
            scores.append(score)

        if len(seen) != ALE_TASK_COUNT:
            raise BenchmarkEvidenceError("ALE task ids must be unique across the complete run")

        score = 100.0 * sum(scores) / ALE_TASK_COUNT
        return {
            "benchmark_id": "agents_last_exam",
            "score": score,
            "unit": "percent",
            "provenance": {"source": source_url, "measured_at": measured_at},
            "runner": {
                "name": "ale_run",
                "version": ALE_VERSION,
                "config": f"agent={agent};model={model};environment={environment};tasks={ALE_TASK_LIST}",
                "dataset": f"{ALE_REPO}@{ALE_COMMIT}:{ALE_TASK_LIST}",
            },
            "raw_result": job,
        }

    def stage(self, job: dict[str, Any]) -> Path:
        return self.store.stage(self.build_evidence(job))
