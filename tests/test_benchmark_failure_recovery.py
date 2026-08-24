from __future__ import annotations

import subprocess
from pathlib import Path

from genesis.autonomous_engineering import AutonomousEngineeringLoop
from genesis.modules.task_queue import PersistentTaskQueue
from genesis.providers import ProviderRegistry


class MalformedBenchmarkProvider:
    name = "malformed-benchmark-coder"

    def available(self) -> bool:
        return True

    def reason(self, prompt: str) -> str:
        del prompt
        return '{"edits":[{"path":"genesis/benchmark_execution.py"'


def git(root: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, text=True)


def make_repo(tmp_path: Path) -> None:
    (tmp_path / "genesis").mkdir()
    (tmp_path / "scripts").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "GENESIS_CONSTITUTION.md").write_text("constitution\n", encoding="utf-8")
    (tmp_path / "GENESIS_BLOCK.json").write_text("{}\n", encoding="utf-8")
    (tmp_path / "scripts" / "secret_guard.py").write_text("# guard\n", encoding="utf-8")
    (tmp_path / "genesis" / "benchmark_execution.py").write_text("READY = False\n", encoding="utf-8")
    (tmp_path / "tests" / "test_baseline.py").write_text("def test_baseline():\n    assert True\n", encoding="utf-8")
    git(tmp_path, "init", "-b", "main")
    git(tmp_path, "config", "user.name", "Test")
    git(tmp_path, "config", "user.email", "test@example.com")
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "-m", "baseline")


def test_benchmark_coding_failure_consumes_retry_budget_and_quarantines(tmp_path: Path) -> None:
    make_repo(tmp_path)
    queue = PersistentTaskQueue(tmp_path / "runtime" / "genesis_tasks.sqlite3")
    task = queue.create(
        "Make SWE-bench Pro executable without fabricating a score",
        module_id="genesis.coding",
        priority=100,
        max_attempts=1,
        payload={
            "task_type": "benchmark_runner_integration",
            "benchmark_id": "swe_bench_pro",
            "context_paths": ["genesis/benchmark_execution.py"],
            "score_fabrication_forbidden": True,
            "requires_independent_validation": True,
        },
    )
    registry = ProviderRegistry(include_bootstrap=False)
    registry.register(MalformedBenchmarkProvider())

    result = AutonomousEngineeringLoop(tmp_path, registry).run_once()

    attempt = result["attempted_tasks"][0]
    updated = queue.get(task.task_id)
    assert attempt["coding_status"] == "provider_or_candidate_error"
    assert updated is not None
    assert updated.state == "quarantined"
    assert updated.attempt_count == 1
    assert len(updated.failure_history) == 1
    assert updated.failure_history[-1]["classification"] == "benchmark_coding_provider_or_candidate_error"
    assert "complete JSON object" in updated.failure_history[-1]["error"]
    assert attempt["failure_accounting"] == {
        "classification": "benchmark_coding_provider_or_candidate_error",
        "attempt_count": 1,
        "max_attempts": 1,
        "state": "quarantined",
        "strategy_generation_can_advance": True,
    }


def test_non_benchmark_failure_keeps_existing_blocked_behavior(tmp_path: Path) -> None:
    make_repo(tmp_path)
    queue = PersistentTaskQueue(tmp_path / "runtime" / "genesis_tasks.sqlite3")
    task = queue.create(
        "Ordinary coding task",
        module_id="genesis.coding",
        priority=100,
        max_attempts=1,
        payload={"context_paths": ["genesis/benchmark_execution.py"]},
    )
    registry = ProviderRegistry(include_bootstrap=False)
    registry.register(MalformedBenchmarkProvider())

    result = AutonomousEngineeringLoop(tmp_path, registry).run_once()

    attempt = result["attempted_tasks"][0]
    updated = queue.get(task.task_id)
    assert attempt["coding_status"] == "provider_or_candidate_error"
    assert "failure_accounting" not in attempt
    assert updated is not None
    assert updated.state == "blocked"
    assert updated.attempt_count == 0
