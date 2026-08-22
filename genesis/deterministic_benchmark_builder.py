from __future__ import annotations

import json
from pathlib import Path

from .coding import CodingModule


class DeterministicBenchmarkIntegrationProvider:
    """Build a pinned benchmark adapter without an LLM.

    This is intentionally a narrow template registry, not a generic code writer.
    Unsupported benchmark tasks return ``None`` so Genesis cannot invent an
    integration or fabricate benchmark evidence.
    """

    name = "genesis-deterministic-benchmark-builder"
    BENCHMARK_ID = "agents_last_exam"
    ALE_REPO = "https://github.com/rdi-berkeley/agents-last-exam"
    ALE_COMMIT = "1c9cc7e6825c8123344b78245e0eaceebfa18fa7"
    ALE_VERSION = "0.1.0"
    ALE_TASK_LIST = "selected_tasks/full.txt"
    ALE_TASK_LIST_BLOB_SHA = "d94c985483153a4dbd169fe63d9300b004fe96f0"
    ALE_TASK_COUNT = 152

    def __init__(self, proposal: dict) -> None:
        self._proposal = proposal

    def available(self) -> bool:
        return True

    def reason(self, prompt: str) -> str:
        del prompt
        return json.dumps(self._proposal, sort_keys=True)

    @staticmethod
    def _replace_once(text: str, old: str, new: str, label: str) -> str:
        if text.count(old) != 1:
            raise RuntimeError(f"benchmark integration anchor changed: {label}")
        return text.replace(old, new, 1)

    @classmethod
    def _adapter_source(cls) -> str:
        return f'''from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from .benchmark_evidence import BenchmarkEvidenceError, CompetitiveBenchmarkEvidenceStore


ALE_REPO = {cls.ALE_REPO!r}
ALE_COMMIT = {cls.ALE_COMMIT!r}
ALE_VERSION = {cls.ALE_VERSION!r}
ALE_TASK_LIST = {cls.ALE_TASK_LIST!r}
ALE_TASK_LIST_BLOB_SHA = {cls.ALE_TASK_LIST_BLOB_SHA!r}
ALE_TASK_COUNT = {cls.ALE_TASK_COUNT}


class AgentsLastExamEvidenceAdapter:
    """Convert a complete pinned ALE full-task run into staged evidence."""

    def __init__(self, root: Path) -> None:
        self.store = CompetitiveBenchmarkEvidenceStore(root)

    @staticmethod
    def _required_text(container: dict[str, Any], key: str) -> str:
        value = str(container.get(key, "")).strip()
        if not value:
            raise BenchmarkEvidenceError(f"{{key}} is required")
        return value

    @staticmethod
    def _validate_timestamp(value: str) -> None:
        try:
            datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise BenchmarkEvidenceError("measured_at must be ISO-8601") from exc

    @classmethod
    def execution_readiness(cls) -> dict[str, Any]:
        return {{
            "benchmark_id": "agents_last_exam",
            "framework_repo": ALE_REPO,
            "framework_commit": ALE_COMMIT,
            "framework_version": ALE_VERSION,
            "task_list": ALE_TASK_LIST,
            "task_list_blob_sha": ALE_TASK_LIST_BLOB_SHA,
            "task_count": ALE_TASK_COUNT,
            "runner": "uv run python -m ale_run run <experiment.yaml>",
            "provider_independent_adapter": True,
        }}

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
                f"Agents' Last Exam requires exactly {{ALE_TASK_COUNT}} pinned task results"
            )

        seen: set[str] = set()
        scores: list[float] = []
        for item in results:
            if not isinstance(item, dict):
                raise BenchmarkEvidenceError("each ALE result must be an object")
            task_id = self._required_text(item, "task_id")
            if task_id in seen:
                raise BenchmarkEvidenceError(f"duplicate ALE task id: {{task_id}}")
            seen.add(task_id)
            status = self._required_text(item, "status")
            if status not in {{"completed", "timeout"}}:
                raise BenchmarkEvidenceError(f"unsupported ALE task status: {{status}}")
            raw_score = item.get("score")
            if isinstance(raw_score, bool) or not isinstance(raw_score, (int, float)):
                raise BenchmarkEvidenceError(f"task {{task_id}} score must be numeric")
            score = float(raw_score)
            if not 0.0 <= score <= 1.0:
                raise BenchmarkEvidenceError(f"task {{task_id}} score must be between 0 and 1")
            if status == "timeout" and score != 0.0:
                raise BenchmarkEvidenceError("timeout ALE tasks must contribute score 0")
            scores.append(score)

        if len(seen) != ALE_TASK_COUNT:
            raise BenchmarkEvidenceError("ALE task ids must be unique across the complete run")

        score = 100.0 * sum(scores) / ALE_TASK_COUNT
        return {{
            "benchmark_id": "agents_last_exam",
            "score": score,
            "unit": "percent",
            "provenance": {{"source": source_url, "measured_at": measured_at}},
            "runner": {{
                "name": "ale_run",
                "version": ALE_VERSION,
                "config": f"agent={{agent}};model={{model}};environment={{environment}};tasks={{ALE_TASK_LIST}}",
                "dataset": f"{{ALE_REPO}}@{{ALE_COMMIT}}:{{ALE_TASK_LIST}}",
            }},
            "raw_result": job,
        }}

    def stage(self, job: dict[str, Any]) -> Path:
        return self.store.stage(self.build_evidence(job))
'''

    @classmethod
    def _test_source(cls) -> str:
        return '''from __future__ import annotations

import json
from pathlib import Path

import pytest

from genesis.agents_last_exam_evidence import (
    ALE_COMMIT,
    ALE_REPO,
    ALE_TASK_COUNT,
    ALE_TASK_LIST,
    ALE_TASK_LIST_BLOB_SHA,
    ALE_VERSION,
    AgentsLastExamEvidenceAdapter,
)
from genesis.benchmark_evidence import BenchmarkEvidenceError
from genesis.benchmark_execution import BenchmarkExecutionPlanner
from genesis.modules.task_queue import PersistentTaskQueue


def complete_job(score: float = 1.0) -> dict:
    return {
        "framework_repo": ALE_REPO,
        "framework_commit": ALE_COMMIT,
        "framework_version": ALE_VERSION,
        "task_list": ALE_TASK_LIST,
        "task_list_blob_sha": ALE_TASK_LIST_BLOB_SHA,
        "source_url": "https://example.invalid/ale/run-1",
        "measured_at": "2026-08-23T00:00:00Z",
        "agent": "genesis",
        "model": "provider-neutral",
        "environment": "official-ale-sandbox",
        "aggregate_score": 0.0,
        "results": [
            {"task_id": f"task/{index:03d}", "status": "completed", "score": score}
            for index in range(ALE_TASK_COUNT)
        ],
    }


def write_reference(root: Path) -> None:
    config = root / "config"
    config.mkdir(parents=True, exist_ok=True)
    (config / "competitive_ai_reference.json").write_text(
        json.dumps({"benchmarks": [{"id": "agents_last_exam", "family": "professional_agentic_work", "unit": "percent"}]}),
        encoding="utf-8",
    )


def test_adapter_derives_score_and_stages_candidate(tmp_path: Path) -> None:
    write_reference(tmp_path)
    job = complete_job(1.0)
    evidence = AgentsLastExamEvidenceAdapter(tmp_path).build_evidence(job)
    assert evidence["score"] == 100.0
    assert evidence["raw_result"]["aggregate_score"] == 0.0
    staged = AgentsLastExamEvidenceAdapter(tmp_path).stage(job)
    payload = json.loads(staged.read_text(encoding="utf-8"))
    assert payload["status"] == "candidate"
    assert payload["requires_independent_validation"] is True


def test_adapter_rejects_incomplete_wrong_revision_and_nonzero_timeout(tmp_path: Path) -> None:
    write_reference(tmp_path)
    adapter = AgentsLastExamEvidenceAdapter(tmp_path)
    missing = complete_job()
    missing["results"].pop()
    with pytest.raises(BenchmarkEvidenceError):
        adapter.build_evidence(missing)
    wrong = complete_job()
    wrong["framework_commit"] = "wrong"
    with pytest.raises(BenchmarkEvidenceError):
        adapter.build_evidence(wrong)
    timeout = complete_job()
    timeout["results"][0]["status"] = "timeout"
    with pytest.raises(BenchmarkEvidenceError):
        adapter.build_evidence(timeout)


def test_planner_stages_real_ale_input(tmp_path: Path) -> None:
    write_reference(tmp_path)
    queue = PersistentTaskQueue(tmp_path / "runtime" / "genesis_tasks.sqlite3")
    task = queue.create(
        "Measure ALE",
        module_id="genesis.evaluation",
        priority=92,
        payload={"task_type": "frontier_benchmark_measurement", "benchmark": {"benchmark_id": "agents_last_exam"}},
    )
    input_dir = tmp_path / "runtime" / "competitive_benchmark_inputs"
    input_dir.mkdir(parents=True, exist_ok=True)
    (input_dir / "agents_last_exam.json").write_text(json.dumps(complete_job(0.5)), encoding="utf-8")
    result = BenchmarkExecutionPlanner(tmp_path).advance(task)
    assert result["status"] == "evidence_staged"
    candidate = json.loads(Path(result["candidate_path"]).read_text(encoding="utf-8"))
    assert candidate["score"] == 50.0
'''

    @classmethod
    def _updated_benchmark_execution(cls, current: str) -> str:
        current = cls._replace_once(
            current,
            "from .modules.task_queue import GenesisTask, PersistentTaskQueue\n"
            "from .terminal_bench_evidence import TerminalBench21EvidenceAdapter",
            "from .agents_last_exam_evidence import AgentsLastExamEvidenceAdapter\n"
            "from .modules.task_queue import GenesisTask, PersistentTaskQueue\n"
            "from .terminal_bench_evidence import TerminalBench21EvidenceAdapter",
            "adapter import",
        )
        current = cls._replace_once(
            current,
            '    EVIDENCE_ADAPTER_BENCHMARKS = {"terminal_bench_2_1"}',
            '    EVIDENCE_ADAPTER_BENCHMARKS = {"agents_last_exam", "terminal_bench_2_1"}',
            "adapter registry",
        )
        old = '''        input_path = self.input_dir / f"{benchmark_id}.json"
        if benchmark_id == "terminal_bench_2_1" and input_path.is_file():
            job = json.loads(input_path.read_text(encoding="utf-8"))
            staged = TerminalBench21EvidenceAdapter(self.root).stage(job)
            return {"status": "evidence_staged", "benchmark_id": benchmark_id, "candidate_path": str(staged)}

        return self._runner_task(task, benchmark_id)'''
        new = '''        input_path = self.input_dir / f"{benchmark_id}.json"
        if benchmark_id == "agents_last_exam":
            if input_path.is_file():
                job = json.loads(input_path.read_text(encoding="utf-8"))
                staged = AgentsLastExamEvidenceAdapter(self.root).stage(job)
                return {"status": "evidence_staged", "benchmark_id": benchmark_id, "candidate_path": str(staged)}
            return {
                "status": "external_execution_required",
                "benchmark_id": benchmark_id,
                "reason": "deterministic ALE evidence adapter is ready; a complete official pinned ALE run is still required",
                "missing": ["official_ale_full_experiment_result"],
                "readiness": AgentsLastExamEvidenceAdapter.execution_readiness(),
                "engineering_assistance_required": True,
                "owner_action_required": False,
            }
        if benchmark_id == "terminal_bench_2_1" and input_path.is_file():
            job = json.loads(input_path.read_text(encoding="utf-8"))
            staged = TerminalBench21EvidenceAdapter(self.root).stage(job)
            return {"status": "evidence_staged", "benchmark_id": benchmark_id, "candidate_path": str(staged)}

        return self._runner_task(task, benchmark_id)'''
        return cls._replace_once(current, old, new, "advance integration")

    @classmethod
    def for_task(cls, root: Path, task, coding: CodingModule) -> "DeterministicBenchmarkIntegrationProvider | None":
        payload = dict(getattr(task, "payload", {}) or {})
        if str(payload.get("task_type") or "") != "benchmark_runner_integration":
            return None
        if str(payload.get("benchmark_id") or "") != cls.BENCHMARK_ID:
            return None
        root = Path(root).resolve()
        adapter_path = root / "genesis" / "agents_last_exam_evidence.py"
        benchmark_path = root / "genesis" / "benchmark_execution.py"
        if not benchmark_path.is_file() or adapter_path.is_file():
            return None
        proposal = {
            "title": "Add deterministic Agents Last Exam evidence integration",
            "rationale": "Pinned official ALE integration; no model call and no self-awarded benchmark score.",
            "files": {
                "genesis/agents_last_exam_evidence.py": cls._adapter_source(),
                "genesis/benchmark_execution.py": cls._updated_benchmark_execution(benchmark_path.read_text(encoding="utf-8")),
                "tests/test_agents_last_exam_evidence.py": cls._test_source(),
            },
        }
        coding.validate_proposal(proposal, cls.name)
        return cls(proposal)
