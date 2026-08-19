from __future__ import annotations

import importlib.util
from pathlib import Path

from genesis.modules.task_queue import PersistentTaskQueue


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "autonomous_engineering.py"


def _load_script():
    spec = importlib.util.spec_from_file_location("autonomous_engineering_script", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_owner_marked_issue_becomes_devlab_task(monkeypatch, tmp_path: Path) -> None:
    target = tmp_path / "genesis" / "budget.py"
    target.parent.mkdir(parents=True)
    target.write_text("VALUE = 1\n", encoding="utf-8")
    script = _load_script()
    monkeypatch.setattr(
        script,
        "_github_open_issues",
        lambda: [
            {
                "number": 91,
                "title": "Reject boolean budgets",
                "body": (
                    "<!-- genesis-devlab-task -->\n"
                    "DevLab-Target: genesis/budget.py\n"
                    "DevLab-Module: genesis.coding\n\n"
                    "Reject boolean values while preserving integer budgets."
                ),
            }
        ],
    )

    created = script.ingest_devlab_issues(tmp_path)
    assert len(created) == 1
    queue = PersistentTaskQueue(tmp_path / "runtime" / "genesis_tasks.sqlite3")
    task = queue.get(created[0])
    assert task is not None
    assert task.module_id == "genesis.coding"
    assert task.payload["executor"] == "genesis.devlab"
    assert task.payload["target_path"] == "genesis/budget.py"
    assert task.payload["attribution"] == "owner_initiated"


def test_unmarked_issue_is_not_ingested(monkeypatch, tmp_path: Path) -> None:
    script = _load_script()
    monkeypatch.setattr(script, "_github_open_issues", lambda: [{"number": 91, "title": "x", "body": "plain issue"}])
    assert script.ingest_devlab_issues(tmp_path) == []
