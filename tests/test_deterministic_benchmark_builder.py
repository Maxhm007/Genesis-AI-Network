from __future__ import annotations

import ast
import json
from pathlib import Path
from types import SimpleNamespace

import genesis.deterministic_coding_fallback as fallback
from genesis.autonomous_engineering import AutonomousEngineeringLoop
from genesis.deterministic_benchmark_builder import DeterministicBenchmarkIntegrationProvider


BENCHMARK_FIXTURE = '''from __future__ import annotations

import json
from pathlib import Path

from .modules.task_queue import GenesisTask, PersistentTaskQueue
from .terminal_bench_evidence import TerminalBench21EvidenceAdapter


class BenchmarkExecutionPlanner:
    EVIDENCE_ADAPTER_BENCHMARKS = {"terminal_bench_2_1"}

    def _runner_task(self, task, benchmark_id):
        return {"status": "runner_work_queued"}

    def advance(self, task):
        benchmark_id = "agents_last_exam"
        input_path = self.input_dir / f"{benchmark_id}.json"
        if benchmark_id == "terminal_bench_2_1" and input_path.is_file():
            job = json.loads(input_path.read_text(encoding="utf-8"))
            staged = TerminalBench21EvidenceAdapter(self.root).stage(job)
            return {"status": "evidence_staged", "benchmark_id": benchmark_id, "candidate_path": str(staged)}

        return self._runner_task(task, benchmark_id)
'''


class ValidateOnlyCoding:
    def __init__(self) -> None:
        self.seen_provider = None
        self.seen_proposal = None

    def validate_proposal(self, proposal: dict, provider_name: str):
        self.seen_provider = provider_name
        self.seen_proposal = proposal
        for path, content in proposal["files"].items():
            if path.endswith(".py"):
                ast.parse(content, filename=path)
        return proposal


def make_fixture(root: Path) -> None:
    (root / "genesis").mkdir()
    (root / "tests").mkdir()
    (root / "genesis" / "benchmark_execution.py").write_text(BENCHMARK_FIXTURE, encoding="utf-8")


def test_agents_last_exam_task_gets_pinned_deterministic_candidate(tmp_path: Path) -> None:
    make_fixture(tmp_path)
    coding = ValidateOnlyCoding()
    task = SimpleNamespace(
        payload={
            "task_type": "benchmark_runner_integration",
            "benchmark_id": "agents_last_exam",
        }
    )

    provider = DeterministicBenchmarkIntegrationProvider.for_task(tmp_path, task, coding)
    assert provider is not None
    proposal = json.loads(provider.reason("ignored"))
    assert coding.seen_provider == "genesis-deterministic-benchmark-builder"
    assert set(proposal["files"]) == {
        "genesis/agents_last_exam_evidence.py",
        "genesis/benchmark_execution.py",
        "tests/test_agents_last_exam_evidence.py",
    }
    adapter = proposal["files"]["genesis/agents_last_exam_evidence.py"]
    assert DeterministicBenchmarkIntegrationProvider.ALE_COMMIT in adapter
    assert DeterministicBenchmarkIntegrationProvider.ALE_TASK_LIST_BLOB_SHA in adapter
    assert "ALE_TASK_COUNT = 152" in adapter
    assert "score = 100.0 * sum(scores) / ALE_TASK_COUNT" in adapter
    assert 'EVIDENCE_ADAPTER_BENCHMARKS = {"agents_last_exam", "terminal_bench_2_1"}' in proposal["files"]["genesis/benchmark_execution.py"]


def test_unsupported_benchmark_is_not_deterministically_invented(tmp_path: Path) -> None:
    make_fixture(tmp_path)
    task = SimpleNamespace(
        payload={
            "task_type": "benchmark_runner_integration",
            "benchmark_id": "unknown_future_benchmark",
        }
    )
    assert DeterministicBenchmarkIntegrationProvider.for_task(tmp_path, task, ValidateOnlyCoding()) is None


def test_existing_adapter_prevents_duplicate_generation(tmp_path: Path) -> None:
    make_fixture(tmp_path)
    (tmp_path / "genesis" / "agents_last_exam_evidence.py").write_text("# already integrated\n", encoding="utf-8")
    task = SimpleNamespace(
        payload={
            "task_type": "benchmark_runner_integration",
            "benchmark_id": "agents_last_exam",
        }
    )
    assert DeterministicBenchmarkIntegrationProvider.for_task(tmp_path, task, ValidateOnlyCoding()) is None


def test_deterministic_wrapper_is_installed_after_provider_policy() -> None:
    assert getattr(AutonomousEngineeringLoop, fallback.INSTALL_MARKER, False) is True
    assert AutonomousEngineeringLoop._attempt_task is fallback._attempt_task_with_deterministic_benchmark


def test_wrapper_uses_deterministic_provider_and_restores_override(monkeypatch, tmp_path: Path) -> None:
    provider = SimpleNamespace(name="genesis-deterministic-benchmark-builder")
    monkeypatch.setattr(
        fallback.DeterministicBenchmarkIntegrationProvider,
        "for_task",
        classmethod(lambda cls, root, task, coding: provider),
    )

    def original(loop, task, runtime):
        selected = loop._coding_provider()
        return {"coding_strategy": "external_non_qwen_provider", "selected": selected.name}

    monkeypatch.setattr(fallback, "_ORIGINAL_ATTEMPT_TASK", original)
    loop = SimpleNamespace(root=tmp_path, coding=object())
    result = fallback._attempt_task_with_deterministic_benchmark(loop, object(), tmp_path)
    assert result["selected"] == provider.name
    assert result["coding_strategy"] == "deterministic_benchmark_integration"
    assert result["provider_policy"] == "deterministic_benchmark_template_then_non_qwen"
    assert "_coding_provider" not in loop.__dict__
