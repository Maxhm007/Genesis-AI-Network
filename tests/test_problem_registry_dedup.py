from __future__ import annotations

import importlib.util
from pathlib import Path

from genesis.modules.task_queue import PersistentTaskQueue


ROOT = Path(__file__).resolve().parents[1]


def _load_script():
    path = ROOT / "scripts" / "autonomous_engineering.py"
    spec = importlib.util.spec_from_file_location("genesis_problem_registry_dedup_script", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _issue(number: int, title: str, body: str = "") -> dict:
    return {
        "number": number,
        "title": title,
        "body": body,
        "html_url": f"https://github.test/issues/{number}",
        "labels": [],
    }


def test_github_issue_links_to_existing_genesis_problem_instead_of_creating_duplicate(monkeypatch, tmp_path: Path):
    module = _load_script()
    queue = PersistentTaskQueue(tmp_path / "runtime" / "genesis_tasks.sqlite3")
    internal, _ = queue.create_unique(
        "autonomous:stale-action-reconciliation",
        "Repair stale Action failure reconciliation for fresh workflow runs.",
        module_id="genesis.coding",
        priority=85,
        payload={"source": "autonomous_discovery", "task_type": "coding"},
    )
    issue = _issue(401, "Repair stale Action failure reconciliation")
    monkeypatch.setattr(module, "_github_open_issues", lambda: [issue])

    report = module.ingest_open_issue_backlog(tmp_path)

    assert report["created_count"] == 0
    assert report["linked_existing_count"] == 1
    row = report["issues"][0]
    assert row["status"] == "linked_existing_problem"
    assert row["deduplicated"] is True
    assert row["task_id"] == internal.task_id
    assert [task.task_id for task in queue.list(limit=100)] == [internal.task_id]


def test_explicit_problem_fingerprint_links_even_when_wording_differs(monkeypatch, tmp_path: Path):
    module = _load_script()
    queue = PersistentTaskQueue(tmp_path / "runtime" / "genesis_tasks.sqlite3")
    internal, _ = queue.create_unique(
        "dashboard-drift",
        "Correct the application status surface using validated runtime evidence.",
        module_id="genesis.application",
        payload={
            "source": "application_inspection",
            "task_type": "application_repair",
            "problem_fingerprint": "problem:dashboard-drift:v1",
        },
    )
    issue = _issue(
        402,
        "Dashboard telemetry is inconsistent",
        "Genesis-Problem-Fingerprint: problem:dashboard-drift:v1\n\nExternal visibility for the same problem.",
    )
    monkeypatch.setattr(module, "_github_open_issues", lambda: [issue])

    report = module.ingest_open_issue_backlog(tmp_path)

    assert report["created_count"] == 0
    assert report["issues"][0]["task_id"] == internal.task_id
    assert report["issues"][0]["status"] == "linked_existing_problem"


def test_scheduled_retry_still_owns_problem_and_blocks_duplicate_intake(monkeypatch, tmp_path: Path):
    module = _load_script()
    queue = PersistentTaskQueue(tmp_path / "runtime" / "genesis_tasks.sqlite3")
    internal, _ = queue.create_unique(
        "autonomous:parser-validation-crash",
        "Repair parser validation crash in autonomous coding intake.",
        module_id="genesis.coding",
        max_attempts=5,
        payload={"source": "autonomous_discovery", "task_type": "coding"},
    )
    queue.transition(internal.task_id, "assigned", module_id=internal.module_id)
    queue.transition(internal.task_id, "running", module_id=internal.module_id)
    failed = queue.record_failure(
        internal.task_id,
        "bounded failure",
        classification="test",
        retry_after_seconds=3600,
        module_id=internal.module_id,
    )
    assert failed.state == "failed"
    assert queue.retryable(failed) is False

    monkeypatch.setattr(module, "_github_open_issues", lambda: [_issue(403, "Repair parser validation crash")])
    report = module.ingest_open_issue_backlog(tmp_path)

    assert report["created_count"] == 0
    assert report["issues"][0]["task_id"] == internal.task_id
    assert report["issues"][0]["status"] == "linked_existing_problem"


def test_unrelated_issue_still_creates_normal_github_backlog_task(monkeypatch, tmp_path: Path):
    module = _load_script()
    queue = PersistentTaskQueue(tmp_path / "runtime" / "genesis_tasks.sqlite3")
    internal, _ = queue.create_unique(
        "autonomous:stale-action-reconciliation",
        "Repair stale Action failure reconciliation for fresh workflow runs.",
        module_id="genesis.coding",
        payload={"source": "autonomous_discovery", "task_type": "coding"},
    )
    monkeypatch.setattr(module, "_github_open_issues", lambda: [_issue(404, "Repair parser validation crash")])

    report = module.ingest_open_issue_backlog(tmp_path)

    assert report["created_count"] == 1
    row = report["issues"][0]
    assert row["status"] == "created"
    assert row["deduplicated"] is False
    assert row["task_id"] != internal.task_id
    assert len(queue.list(limit=100)) == 2
