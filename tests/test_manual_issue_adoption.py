from __future__ import annotations

import importlib.util
from pathlib import Path

from genesis.modules.task_queue import PersistentTaskQueue


ROOT = Path(__file__).resolve().parents[1]


def _load_script():
    path = ROOT / "scripts" / "autonomous_engineering.py"
    spec = importlib.util.spec_from_file_location("genesis_manual_issue_adoption_script", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_manual_issue_adopts_matching_existing_task_without_duplicate(monkeypatch, tmp_path: Path):
    module = _load_script()
    queue = PersistentTaskQueue(tmp_path / "runtime" / "genesis_tasks.sqlite3")
    existing, created = queue.create_unique(
        "internal-memory-reliability",
        "Improve memory reliability persistence recovery behavior",
        module_id="genesis.self_development",
        payload={"task_type": "self_improvement", "source": "genesis.self_learning"},
    )
    assert created is True

    issue = {
        "number": 88,
        "title": "Improve memory reliability persistence recovery",
        "body": "Make the existing Genesis work complete and verifiable.",
        "html_url": "https://github.test/issues/88",
        "labels": [],
    }
    monkeypatch.setattr(module, "_github_open_issues", lambda: [issue])

    result = module.ingest_open_issue_backlog(tmp_path)

    row = result["issues"][0]
    assert row["status"] == "linked_existing_problem"
    assert row["task_id"] == existing.task_id
    assert result["created_count"] == 0
    assert result["linked_existing_count"] == 1
    assert len(queue.list(limit=20)) == 1

    adopted = queue.get(existing.task_id)
    assert adopted is not None
    assert adopted.payload["github_issue_number"] == 88
    assert adopted.payload["github_issue_url"] == "https://github.test/issues/88"
    assert adopted.payload["github_issue_authoritative"] is True
    assert adopted.payload["execution_lane"] == "github_issue"
