from __future__ import annotations

import subprocess
from pathlib import Path

from genesis.autonomous_engineering import AutonomousEngineeringLoop
from genesis.modules.task_queue import PersistentTaskQueue
from genesis.providers import ProviderRegistry


class FakeCodingProvider:
    name = "fake-coder"

    def available(self) -> bool:
        return True

    def reason(self, prompt: str) -> str:
        return '{"title":"Add bounded helper","rationale":"test","files":{"genesis/auto_helper.py":"VALUE = 1\\n"}}'


class SelectiveCodingProvider:
    name = "selective-coder"

    def available(self) -> bool:
        return True

    def reason(self, prompt: str) -> str:
        if "First task must fail" in prompt:
            raise TimeoutError("simulated provider timeout")
        return '{"title":"Recover on next task","rationale":"test fallback","files":{"genesis/recovered_helper.py":"VALUE = 2\\n"}}'


def git(root: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, text=True)


def make_repo(tmp_path: Path) -> None:
    (tmp_path / "genesis").mkdir()
    (tmp_path / "scripts").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "GENESIS_CONSTITUTION.md").write_text("constitution\n")
    (tmp_path / "GENESIS_BLOCK.json").write_text("{}\n")
    (tmp_path / "scripts" / "secret_guard.py").write_text("# guard\n")
    (tmp_path / "tests" / "test_baseline.py").write_text("def test_baseline():\n    assert True\n")
    git(tmp_path, "init", "-b", "main")
    git(tmp_path, "config", "user.name", "Test")
    git(tmp_path, "config", "user.email", "test@example.com")
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "-m", "baseline")


def test_clean_security_scan_can_idle(tmp_path: Path):
    make_repo(tmp_path)
    loop = AutonomousEngineeringLoop(tmp_path, ProviderRegistry(include_bootstrap=False))
    result = loop.run_once()
    assert result["security"]["status"] == "pass"
    assert result["coding_status"] == "idle"
    assert result["attempted_tasks"] == []


def test_priority_engineering_task_creates_security_reviewed_candidate(tmp_path: Path):
    make_repo(tmp_path)
    queue = PersistentTaskQueue(tmp_path / "runtime" / "genesis_tasks.sqlite3")
    queue.create("Add a tiny tested helper", module_id="genesis.coding", priority=90)
    registry = ProviderRegistry(include_bootstrap=False)
    registry.register(FakeCodingProvider())
    loop = AutonomousEngineeringLoop(tmp_path, registry)
    result = loop.run_once()
    assert result["coding_status"] == "candidate_created"
    assert result["candidate"]["committed"] is True
    assert result["candidate_security"]["status"] == "pass"
    assert len(result["attempted_tasks"]) == 1
    assert result["candidate"]["changed_files"] == ["genesis/auto_helper.py"] or tuple(result["candidate"]["changed_files"]) == ("genesis/auto_helper.py",)


def test_failed_high_priority_task_does_not_block_next_task(tmp_path: Path):
    make_repo(tmp_path)
    queue = PersistentTaskQueue(tmp_path / "runtime" / "genesis_tasks.sqlite3")
    first = queue.create("First task must fail", module_id="genesis.coding", priority=100)
    second = queue.create("Second task should recover", module_id="genesis.coding", priority=90)
    registry = ProviderRegistry(include_bootstrap=False)
    registry.register(SelectiveCodingProvider())
    loop = AutonomousEngineeringLoop(tmp_path, registry)
    result = loop.run_once()

    assert len(result["attempted_tasks"]) == 2
    assert result["attempted_tasks"][0]["task"]["task_id"] == first.task_id
    assert result["attempted_tasks"][0]["coding_status"] == "provider_or_candidate_error"
    assert queue.get(first.task_id).state == "blocked"
    assert result["attempted_tasks"][1]["task"]["task_id"] == second.task_id
    assert result["coding_status"] == "candidate_created"
    assert result["candidate_security"]["status"] == "pass"
    assert queue.get(second.task_id).state == "review"
