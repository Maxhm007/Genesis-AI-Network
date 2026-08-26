from __future__ import annotations

from pathlib import Path

from genesis.github_issue_task_router import AUTONOMOUS_REPAIR_LABEL, GENESIS_TASK_LABEL, route_unbacked_tasks
from genesis.issue_backpressure import (
    DEFAULT_MAX_ACTIVE_AUTONOMOUS_ISSUES,
    active_capacity_count,
    bypasses_backpressure,
    capacity_limited_task,
    configured_max_active,
)
from genesis.modules.task_queue import PersistentTaskQueue


class FakeGithub:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict | None]] = []
        self.issues: list[dict] = []
        self.next_issue = 500

    def __call__(self, method: str, path: str, payload: dict | None = None):
        self.calls.append((method, path, payload))
        if method == "GET" and path.startswith("/labels"):
            return [{"name": GENESIS_TASK_LABEL}, {"name": AUTONOMOUS_REPAIR_LABEL}]
        if method == "GET" and path.startswith("/issues?"):
            return list(self.issues)
        if method == "POST" and path == "/issues":
            self.next_issue += 1
            issue = {
                "number": self.next_issue,
                "html_url": f"https://github.test/issues/{self.next_issue}",
                "title": str((payload or {}).get("title") or ""),
                "body": str((payload or {}).get("body") or ""),
                "labels": [{"name": name} for name in (payload or {}).get("labels", [])],
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


def _queue(root: Path) -> PersistentTaskQueue:
    return PersistentTaskQueue(root / "runtime" / "genesis_tasks.sqlite3")


def _capacity_issue(number: int, *, state: str = "open", task_type: str = "new_capability") -> dict:
    return {
        "number": number,
        "state": state,
        "labels": [{"name": GENESIS_TASK_LABEL}],
        "body": (
            f"<!-- genesis-task-id:task-existing-{number} -->\n"
            f"Genesis-Problem-Fingerprint: genesis-objective:{number:032x}\n"
            f"- **Genesis task ID:** `task-existing-{number}`\n"
            f"- **Task type:** `{task_type}`\n"
            "- **Source:** `genesis.evolution_learning`\n\n"
            "### Objective\nExisting distinct capacity work.\n\n"
            "### Acceptance\nPreserve validation.\n"
        ),
    }


def _issue_posts(github: FakeGithub) -> list[dict]:
    return [
        payload or {}
        for method, path, payload in github.calls
        if method == "POST" and path == "/issues"
    ]


def test_backlog_configuration_defaults_and_bounds() -> None:
    assert configured_max_active({}) == DEFAULT_MAX_ACTIVE_AUTONOMOUS_ISSUES == 20
    assert configured_max_active({"GENESIS_MAX_ACTIVE_AUTONOMOUS_ISSUES": "7"}) == 7
    assert configured_max_active({"GENESIS_MAX_ACTIVE_AUTONOMOUS_ISSUES": "invalid"}) == 20
    assert configured_max_active({"GENESIS_MAX_ACTIVE_AUTONOMOUS_ISSUES": "0"}) == 20
    assert configured_max_active({"GENESIS_MAX_ACTIVE_AUTONOMOUS_ISSUES": "9999"}) == 500


def test_capacity_count_excludes_repair_work() -> None:
    issues = [_capacity_issue(1), _capacity_issue(2, task_type="self_repair"), _capacity_issue(3, state="closed")]
    assert active_capacity_count(issues) == 1


def test_full_backlog_defers_research_candidate_without_mutating_task(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("GENESIS_MAX_ACTIVE_AUTONOMOUS_ISSUES", "1")
    queue = _queue(tmp_path)
    task, _ = queue.create_unique(
        "research-waits",
        "Add one bounded learned capability for retry-safe artifact reuse.",
        module_id="genesis.coding",
        priority=78,
        payload={
            "task_type": "new_capability",
            "source": "genesis.evolution_learning",
            "target_path": "genesis/learned_capabilities.py",
        },
    )
    github = FakeGithub()
    github.issues.append(_capacity_issue(400))

    result = route_unbacked_tasks(tmp_path, requester=github)

    assert result["status"] == "ok"
    assert result["backpressure"]["active_capacity_issues"] == 1
    assert [row["task_id"] for row in result["deferred"]] == [task.task_id]
    assert _issue_posts(github) == []
    unchanged = queue.get(task.task_id)
    assert unchanged is not None
    assert unchanged.state == "new"
    assert int(unchanged.payload.get("github_issue_number") or 0) == 0


def test_repair_bypasses_full_research_backlog(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("GENESIS_MAX_ACTIVE_AUTONOMOUS_ISSUES", "1")
    queue = _queue(tmp_path)
    repair, _ = queue.create_unique(
        "repair-bypass",
        "Repair a concrete failing validator path.",
        module_id="genesis.coding",
        priority=96,
        payload={"task_type": "self_repair", "source": "genesis.issue_discovery", "target_path": "genesis/example.py"},
    )
    assert bypasses_backpressure(repair) is True
    assert capacity_limited_task(repair) is False
    github = FakeGithub()
    github.issues.append(_capacity_issue(400))

    result = route_unbacked_tasks(tmp_path, requester=github)

    assert [row["task_id"] for row in result["bound"]] == [repair.task_id]
    assert len(_issue_posts(github)) == 1


def test_owner_prioritized_work_bypasses_capacity(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("GENESIS_MAX_ACTIVE_AUTONOMOUS_ISSUES", "1")
    queue = _queue(tmp_path)
    task, _ = queue.create_unique(
        "owner-priority",
        "Owner-prioritized bounded capability task.",
        module_id="genesis.coding",
        priority=100,
        payload={
            "task_type": "new_capability",
            "source": "genesis.evolution_learning",
            "owner_prioritized": True,
        },
    )
    github = FakeGithub()
    github.issues.append(_capacity_issue(400))

    result = route_unbacked_tasks(tmp_path, requester=github)

    assert [row["task_id"] for row in result["bound"]] == [task.task_id]
    assert len(_issue_posts(github)) == 1


def test_capacity_release_admits_highest_priority_then_oldest(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("GENESIS_MAX_ACTIVE_AUTONOMOUS_ISSUES", "1")
    queue = _queue(tmp_path)
    low, _ = queue.create_unique(
        "low",
        "Add low-priority learned capability.",
        module_id="genesis.coding",
        priority=60,
        payload={"task_type": "new_capability", "source": "genesis.evolution_learning"},
    )
    high, _ = queue.create_unique(
        "high",
        "Add high-priority learned capability.",
        module_id="genesis.coding",
        priority=90,
        payload={"task_type": "new_capability", "source": "genesis.evolution_learning"},
    )
    github = FakeGithub()
    blocker = _capacity_issue(400)
    github.issues.append(blocker)

    first = route_unbacked_tasks(tmp_path, requester=github)
    assert {row["task_id"] for row in first["deferred"]} == {low.task_id, high.task_id}
    assert _issue_posts(github) == []

    blocker["state"] = "closed"
    github.calls.clear()
    second = route_unbacked_tasks(tmp_path, requester=github)

    assert [row["task_id"] for row in second["bound"]] == [high.task_id]
    assert [row["task_id"] for row in second["deferred"]] == [low.task_id]
    assert len(_issue_posts(github)) == 1


def test_dedupe_reuses_same_issue_even_when_capacity_fills(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("GENESIS_MAX_ACTIVE_AUTONOMOUS_ISSUES", "1")
    queue = _queue(tmp_path)
    lesson = "Autonomously add one bounded executable Genesis capability named learned_1111111111111111. Use the learned idea: validate JSON before persistence."
    first, _ = queue.create_unique(
        "same-idea-1",
        lesson,
        module_id="genesis.coding",
        priority=80,
        payload={
            "task_type": "new_capability",
            "source": "genesis.evolution_learning",
            "target_path": "genesis/learned_capabilities.py",
        },
    )
    second, _ = queue.create_unique(
        "same-idea-2",
        lesson.replace("learned_1111111111111111", "learned_2222222222222222"),
        module_id="genesis.coding",
        priority=79,
        payload={
            "task_type": "new_capability",
            "source": "genesis.evolution_learning",
            "target_path": "genesis/learned_capabilities.py",
        },
    )
    github = FakeGithub()

    result = route_unbacked_tasks(tmp_path, requester=github)

    assert len(_issue_posts(github)) == 1
    rebound_first = queue.get(first.task_id)
    rebound_second = queue.get(second.task_id)
    assert rebound_first is not None and rebound_second is not None
    assert rebound_first.payload["github_issue_number"] == rebound_second.payload["github_issue_number"]
    assert result["deferred"] == []
