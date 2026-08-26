from __future__ import annotations

from pathlib import Path

from genesis.github_issue_task_router import (
    AUTONOMOUS_REPAIR_LABEL,
    GENESIS_TASK_LABEL,
    issue_authority_enabled,
    route_unbacked_tasks,
)
from genesis.modules.task_queue import PersistentTaskQueue
from genesis.task_router import TaskRouterModule


def _queue(root: Path) -> PersistentTaskQueue:
    return PersistentTaskQueue(root / "runtime" / "genesis_tasks.sqlite3")


class FakeGithub:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict | None]] = []
        self.issues: list[dict] = []
        self.next_issue = 41

    def __call__(self, method: str, path: str, payload: dict | None = None):
        self.calls.append((method, path, payload))
        if method == "GET" and path.startswith("/labels"):
            return [{"name": GENESIS_TASK_LABEL}]
        if method == "GET" and path.startswith("/issues?"):
            return list(self.issues)
        if method == "POST" and path == "/issues":
            self.next_issue += 1
            issue = {
                "number": self.next_issue,
                "html_url": f"https://github.com/Maxhm007/Genesis-AI-Network/issues/{self.next_issue}",
                "title": str((payload or {}).get("title") or ""),
                "body": str((payload or {}).get("body") or ""),
                "state": "open",
            }
            self.issues.append(issue)
            return issue
        if method == "PATCH" and path.startswith("/issues/"):
            number = int(path.rsplit("/", 1)[1])
            for issue in self.issues:
                if int(issue["number"]) == number:
                    issue.update(payload or {})
                    return dict(issue)
        return None


def test_unbacked_task_creates_issue_and_binds_same_task(tmp_path: Path) -> None:
    queue = _queue(tmp_path)
    task, created = queue.create_unique(
        "hidden-work",
        "Repair a concrete autonomous reliability defect",
        module_id="genesis.coding",
        payload={"task_type": "self_repair", "target_path": "genesis/example.py"},
    )
    assert created is True

    github = FakeGithub()
    result = route_unbacked_tasks(tmp_path, requester=github)

    assert result["status"] == "ok"
    assert result["candidate_count"] == 1
    assert len(result["bound"]) == 1
    updated = queue.get(task.task_id)
    assert updated is not None
    assert updated.payload["github_issue_number"] == 42
    assert updated.payload["execution_lane"] == "github_issue"
    assert updated.payload["github_issue_authoritative"] is True
    assert len(queue.list(limit=20)) == 1
    issue_creates = [
        payload
        for method, path, payload in github.calls
        if method == "POST" and path == "/issues"
    ]
    assert len(issue_creates) == 1
    assert issue_creates[0] is not None
    assert issue_creates[0]["labels"] == [GENESIS_TASK_LABEL, AUTONOMOUS_REPAIR_LABEL]


def test_specialist_execution_issue_is_reused_for_source_task(tmp_path: Path) -> None:
    queue = _queue(tmp_path)
    source, _ = queue.create_unique(
        "source-improvement",
        "Improve Genesis memory reliability",
        module_id="genesis.self_development",
        payload={"task_type": "self_improvement"},
    )
    execution, _ = queue.create_unique(
        "issue-execution",
        "Resolve the Issue-backed memory improvement",
        module_id="genesis.coding",
        payload={
            "task_type": "github_issue_development",
            "github_issue_number": 77,
            "github_issue_url": "https://github.com/Maxhm007/Genesis-AI-Network/issues/77",
            "source_self_improvement_task_id": source.task_id,
        },
    )
    assert execution.payload["github_issue_number"] == 77

    github = FakeGithub()
    result = route_unbacked_tasks(tmp_path, requester=github)

    rebound = queue.get(source.task_id)
    assert rebound is not None
    assert rebound.payload["github_issue_number"] == 77
    assert result["adopted"][0]["task_id"] == source.task_id
    assert not any(method == "POST" and path == "/issues" for method, path, _ in github.calls)


def test_github_failure_leaves_unbacked_task_non_executable(tmp_path: Path) -> None:
    queue = _queue(tmp_path)
    task, _ = queue.create_unique(
        "must-not-run",
        "Do not execute unless a GitHub Issue exists",
        module_id="genesis.coding",
    )

    result = route_unbacked_tasks(tmp_path, requester=lambda *_: None)

    assert result["status"] == "blocked"
    unchanged = queue.get(task.task_id)
    assert unchanged is not None
    assert int(unchanged.payload.get("github_issue_number") or 0) == 0
    assert unchanged.state == "new"


def test_temp_test_runtime_does_not_mutate_real_github(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("GENESIS_FORCE_GITHUB_TASK_AUTHORITY", raising=False)
    monkeypatch.setenv("GITHUB_WORKSPACE", str(tmp_path / "actual-checkout"))
    assert issue_authority_enabled(tmp_path) is False

    queue = _queue(tmp_path)
    queue.create_unique("test-only", "Temporary test task", module_id="genesis.coding")
    result = route_unbacked_tasks(tmp_path)

    assert result["status"] == "not_repository_runtime"
    assert result["enforced"] is False


def test_task_router_refuses_unbacked_production_task(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("GENESIS_FORCE_GITHUB_TASK_AUTHORITY", "1")
    router = TaskRouterModule(tmp_path)
    task, _ = router.queue.create_unique(
        "production-unbacked",
        "This must wait for an Issue",
        module_id="genesis.coding",
    )
    monkeypatch.setattr(
        "genesis.task_router.route_unbacked_tasks",
        lambda _root: {
            "status": "blocked",
            "enforced": True,
            "candidate_count": 1,
            "bound": [],
            "adopted": [],
            "blocked": [task.task_id],
        },
    )

    result = router.assign_next()

    assert result["status"] == "waiting_for_github_issue"
    assert result["decision"] is None
    unchanged = router.queue.get(task.task_id)
    assert unchanged is not None
    assert unchanged.state == "new"
