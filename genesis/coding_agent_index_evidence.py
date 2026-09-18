from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from .benchmark_evidence import BenchmarkEvidenceError, CompetitiveBenchmarkEvidenceStore

CODING_AGENT_INDEX_VERSION = "1.5"
CODING_AGENT_INDEX_SOURCE = "https://artificialanalysis.ai/methodology/coding-agents-benchmarking"
COMPONENTS: dict[str, dict[str, Any]] = {
    "deep_swe_v1_1": {"name": "DeepSWE v1.1", "task_count": 113},
    "terminal_bench_4_0": {"name": "Terminal-Bench 4.0", "task_count": 66},
    "swe_atlas_qna": {"name": "SWE-Atlas-QnA", "task_count": 124},
}
ATTEMPTS_PER_TASK = 3


class CodingAgentIndexEvidenceAdapter:
    """Rebuild Artificial Analysis Coding Agent Index v1.5 from task-level outcomes.

    The adapter never accepts a caller-supplied aggregate score. Each component
    score is recomputed from exactly three binary attempts for every task and the
    final index is the equal-weight mean of the three component scores.
    """

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
            "benchmark_id": "coding_agent_index",
            "index_version": CODING_AGENT_INDEX_VERSION,
            "methodology": CODING_AGENT_INDEX_SOURCE,
            "components": {
                key: {
                    "name": value["name"],
                    "task_count": value["task_count"],
                    "attempts_per_task": ATTEMPTS_PER_TASK,
                }
                for key, value in COMPONENTS.items()
            },
            "aggregation": "equal_weight_mean_of_component_pass_at_1",
            "provider_independent_adapter": True,
        }

    @staticmethod
    def _attempt_passed(value: Any) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, int) and value in {0, 1}:
            return bool(value)
        raise BenchmarkEvidenceError("benchmark attempts must be boolean or binary 0/1")

    def _component_score(self, component_id: str, component: dict[str, Any]) -> float:
        spec = COMPONENTS[component_id]
        if self._required_text(component, "benchmark_id") != component_id:
            raise BenchmarkEvidenceError(f"component benchmark_id must be {component_id}")
        if int(component.get("task_count", -1)) != spec["task_count"]:
            raise BenchmarkEvidenceError(f"{component_id} task_count must be {spec['task_count']}")
        if int(component.get("attempts_per_task", -1)) != ATTEMPTS_PER_TASK:
            raise BenchmarkEvidenceError(f"{component_id} requires exactly {ATTEMPTS_PER_TASK} attempts per task")
        self._required_text(component, "dataset")
        self._required_text(component, "dataset_revision")
        self._required_text(component, "runner_name")
        self._required_text(component, "runner_version")
        self._required_text(component, "runner_config")
        source_url = self._required_text(component, "source_url")
        if not source_url.startswith("https://"):
            raise BenchmarkEvidenceError(f"{component_id} source_url must be HTTPS")

        tasks = component.get("tasks")
        if not isinstance(tasks, list) or len(tasks) != spec["task_count"]:
            raise BenchmarkEvidenceError(f"{component_id} requires exactly {spec['task_count']} task results")
        seen: set[str] = set()
        passed = 0
        attempts = 0
        for row in tasks:
            if not isinstance(row, dict):
                raise BenchmarkEvidenceError(f"{component_id} task result must be an object")
            task_id = self._required_text(row, "task_id")
            if task_id in seen:
                raise BenchmarkEvidenceError(f"duplicate {component_id} task_id: {task_id}")
            seen.add(task_id)
            outcomes = row.get("attempts")
            if not isinstance(outcomes, list) or len(outcomes) != ATTEMPTS_PER_TASK:
                raise BenchmarkEvidenceError(f"{component_id} task {task_id} must contain exactly three attempts")
            normalized = [self._attempt_passed(item) for item in outcomes]
            passed += sum(normalized)
            attempts += len(normalized)
        return 100.0 * passed / attempts

    def build_evidence(self, job: dict[str, Any]) -> dict[str, Any]:
        if self._required_text(job, "index_version") != CODING_AGENT_INDEX_VERSION:
            raise BenchmarkEvidenceError(f"index_version must be {CODING_AGENT_INDEX_VERSION}")
        source_url = self._required_text(job, "source_url")
        if not source_url.startswith("https://"):
            raise BenchmarkEvidenceError("source_url must be an HTTPS provenance URL")
        measured_at = self._required_text(job, "measured_at")
        self._validate_timestamp(measured_at)
        agent = self._required_text(job, "agent")
        model = self._required_text(job, "model")
        harness = self._required_text(job, "harness")

        components = job.get("components")
        if not isinstance(components, dict) or set(components) != set(COMPONENTS):
            raise BenchmarkEvidenceError("components must contain exactly the three Coding Agent Index v1.5 benchmarks")
        scores = {
            component_id: self._component_score(component_id, dict(components[component_id]))
            for component_id in COMPONENTS
        }
        score = sum(scores.values()) / len(scores)

        raw_result = dict(job)
        raw_result["computed_component_scores"] = scores
        raw_result["computed_index"] = score
        return {
            "benchmark_id": "coding_agent_index",
            "score": score,
            "unit": "index",
            "provenance": {"source": source_url, "measured_at": measured_at},
            "runner": {
                "name": "artificial-analysis-coding-agent-index-compatible",
                "version": CODING_AGENT_INDEX_VERSION,
                "config": (
                    f"agent={agent};model={model};harness={harness};"
                    f"attempts_per_task={ATTEMPTS_PER_TASK};aggregation=equal_weight"
                ),
                "dataset": "Coding Agent Index v1.5: DeepSWE v1.1 + Terminal-Bench 4.0 + SWE-Atlas-QnA",
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
        original = dict(raw)
        original.pop("computed_component_scores", None)
        original.pop("computed_index", None)
        rebuilt = self.store.validate(self.build_evidence(original))
        if candidate != rebuilt:
            raise BenchmarkEvidenceError(
                "staged Coding Agent Index candidate does not match independently rebuilt evidence"
            )
        return rebuilt
