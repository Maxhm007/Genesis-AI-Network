import json
from pathlib import Path

from genesis.issue_discovery import GenesisIssueDiscoveryEngine
from genesis.modules.task_queue import PersistentTaskQueue


class FakeIssueProvider:
    name = "fake-coding-provider"

    def available(self) -> bool:
        return True

    def reason(self, prompt: str) -> str:
        assert "RISK_SCORE:" in prompt
        assert "SOURCE:" in prompt
        return json.dumps(
            {
                "decision": "issue",
                "summary": "A boundary value can be accepted without validation.",
                "acceptance": "Invalid boundary values are rejected while valid values remain unchanged.",
                "confidence": "high",
            }
        )


class BootstrapOnlyProvider(FakeIssueProvider):
    name = "genesis-bootstrap"


def _write(root: Path, relative: str, source: str) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")


def test_risk_ranking_is_not_smallest_file_first(tmp_path: Path) -> None:
    _write(tmp_path, "genesis/safe.py", "def value(x):\n    return x\n")
    _write(
        tmp_path,
        "genesis/risky.py",
        "import subprocess\n\ndef run(value):\n    try:\n        subprocess.run(['echo', str(value)], check=False)\n    except Exception:\n        return None\n",
    )
    _write(tmp_path, "tests/test_safe.py", "def test_safe():\n    assert True\n")

    ranked = GenesisIssueDiscoveryEngine(tmp_path).rank_candidates()

    assert ranked[0].path == "genesis/risky.py"
    assert "subprocess_or_shell_boundary" in ranked[0].reasons
    assert "broad_exception_handler" in ranked[0].reasons


def test_protected_control_plane_is_not_autonomous_repair_target(tmp_path: Path) -> None:
    _write(tmp_path, "genesis/security.py", "def unsafe():\n    try:\n        return bool('false')\n    except:\n        return False\n")
    _write(tmp_path, "genesis/worker.py", "def worker():\n    return 1\n")

    engine = GenesisIssueDiscoveryEngine(tmp_path)

    assert "genesis/security.py" not in engine.rank_paths(include_protected=False)
    assert "genesis/security.py" in engine.rank_paths(include_protected=True)


def test_confirmed_issue_becomes_persistent_engineering_task(tmp_path: Path) -> None:
    _write(tmp_path, "genesis/service.py", "def normalize(value):\n    return bool(value)\n")
    _write(tmp_path, "tests/test_service.py", "def test_placeholder():\n    assert True\n")
    queue = PersistentTaskQueue(tmp_path / "runtime" / "tasks.sqlite3")
    engine = GenesisIssueDiscoveryEngine(tmp_path)

    first = engine.discover_and_enqueue(queue, FakeIssueProvider())
    second = engine.discover_and_enqueue(queue, FakeIssueProvider())

    assert first["status"] == "issue_enqueued"
    assert second["status"] == "issue_already_known"
    assert first["task_id"] == second["task_id"]
    task = queue.get(first["task_id"])
    assert task is not None
    assert task.module_id == "genesis.coding"
    assert task.payload["source"] == "genesis.issue_discovery"
    assert task.payload["context_paths"] == ["genesis/service.py", "tests/test_service.py"]
    assert task.priority >= 55
    assert engine.last_result_path.is_file()
    assert engine.history_path.is_file()


def test_bootstrap_provider_cannot_assert_code_issue(tmp_path: Path) -> None:
    _write(tmp_path, "genesis/service.py", "def normalize(value):\n    return bool(value)\n")
    queue = PersistentTaskQueue(tmp_path / "runtime" / "tasks.sqlite3")

    result = GenesisIssueDiscoveryEngine(tmp_path).discover_and_enqueue(queue, BootstrapOnlyProvider())

    assert result["status"] == "blocked"
    assert result["reason"] == "non_bootstrap_provider_required"
    assert queue.list(limit=10) == []
