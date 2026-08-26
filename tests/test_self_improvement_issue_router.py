from __future__ import annotations

from pathlib import Path

from genesis.modules.task_queue import PersistentTaskQueue
from genesis.self_improvement_issue_router import (
    ROUTER_PAUSE_PREFIX,
    SELF_IMPROVEMENT_LABEL,
    create_planned_self_improvement_task,
    route_self_improvement,
)


class FakeGitHub:
    def __init__(self) -> None:
        self.labels: list[dict] = []
        self.issues: list[dict] = []
        self.next_issue = 701

    def request(self, method: str, path: str, payload: dict | None = None):
        if method == "GET" and path == "/labels?per_page=100":
            return list(self.labels)
        if method == "POST" and path == "/labels":
            row = dict(payload or {})
            self.labels.append(row)
            return row
        if method == "GET" and path.startswith("/issues?state=all&labels="):
            return list(self.issues)
        if method == "POST" and path == "/issues":
            row = {
                "number": self.next_issue,
                "title": str((payload or {}).get("title") or ""),
                "body": str((payload or {}).get("body") or ""),
                "labels": [{"name": value} for value in (payload or {}).get("labels", [])],
                "state": "open",
                "html_url": f"https://github.test/issues/{self.next_issue}",
            }
            self.next_issue += 1
            self.issues.append(row)
            return row
        if method == "PATCH" and path.startswith("/issues/"):
            number = int(path.rsplit("/", 1)[1])
            for row in self.issues:
                if row["number"] == number:
                    row.update(payload or {})
                    return dict(row)
            return None
        raise AssertionError((method, path, payload))


def _source_task(root: Path, *, task_type: str = "competitive_ai_improvement", state: str = "new"):
    queue = PersistentTaskQueue(root / "runtime" / "genesis_tasks.sqlite3")
    task, _ = queue.create_unique(
        f"self-improvement:{task_type}",
        "Raise measured Genesis capability without changing score logic or weakening validation.",
        module_id="genesis.capability",
        priority=100,
        payload={
            "task_type": task_type,
            "required_outcome": "Produce real evidence or one bounded validated improvement.",
        },
        max_attempts=4,
    )
    if state == "assigned":
        task = queue.transition(task.task_id, "assigned", module_id="genesis.capability")
    elif state == "running":
        task = queue.transition(task.task_id, "assigned", module_id="genesis.capability")
        task = queue.transition(task.task_id, "running", module_id="genesis.capability")
    return queue, task


def test_internal_self_improvement_becomes_one_issue_backed_task(tmp_path: Path) -> None:
    queue, source = _source_task(tmp_path)
    github = FakeGitHub()

    report = route_self_improvement(tmp_path, requester=github.request)

    assert report["status"] == "ok"
    assert len(report["routed"]) == 1
    paused = queue.get(source.task_id)
    assert paused is not None
    assert paused.state == "paused"
    assert str(paused.state_reason).startswith(ROUTER_PAUSE_PREFIX)

    execution = queue.get(report["routed"][0]["execution_task_id"])
    assert execution is not None
    assert execution.payload["task_type"] == "competitive_ai_improvement"
    assert execution.payload["source"] == "github_self_improvement_issue"
    assert execution.payload["execution_lane"] == "github_issue"
    assert execution.payload["source_self_improvement_task_id"] == source.task_id
    assert execution.payload["github_issue_number"] == 701
    assert execution.payload["close_github_issue_after_promotion"] is False
    assert execution.payload["requires_independent_validation"] is True

    assert github.labels[0]["name"] == SELF_IMPROVEMENT_LABEL
    assert github.issues[0]["title"].startswith("[Genesis Self Improvement]")
    assert f"<!-- genesis-self-improvement-source:{source.task_id} -->" in github.issues[0]["body"]
    assert "authoritative execution lane" in github.issues[0]["body"]


def test_research_driven_existing_capability_upgrade_is_issue_backed(tmp_path: Path) -> None:
    target = tmp_path / "genesis" / "coding.py"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("VALUE = 1\n", encoding="utf-8")
    queue = PersistentTaskQueue(tmp_path / "runtime" / "genesis_tasks.sqlite3")
    source, _ = queue.create_unique(
        "research-upgrade",
        "Apply a research-backed reliability improvement to coding.",
        module_id="genesis.coding",
        priority=95,
        payload={
            "task_type": "research_upgrade",
            "source": "genesis.evolution_learning",
            "target_path": "genesis/coding.py",
            "context_paths": ["genesis/coding.py"],
        },
    )
    github = FakeGitHub()

    report = route_self_improvement(tmp_path, requester=github.request)

    assert len(report["routed"]) == 1
    execution = queue.get(report["routed"][0]["execution_task_id"])
    assert execution is not None
    assert execution.payload["target_path"] == "genesis/coding.py"
    assert execution.payload["close_github_issue_after_promotion"] is True
    assert queue.get(source.task_id).state == "paused"


def test_self_improvement_routing_is_idempotent(tmp_path: Path) -> None:
    queue, source = _source_task(tmp_path, task_type="gene_velocity_improvement")
    github = FakeGitHub()

    first = route_self_improvement(tmp_path, requester=github.request)
    second = route_self_improvement(tmp_path, requester=github.request)

    assert len(first["routed"]) == 1
    assert second["routed"] == []
    assert len(second["already_routed"]) == 1
    assert len(github.issues) == 1
    executions = [
        task for task in queue.list(limit=100)
        if task.payload.get("source_self_improvement_task_id") == source.task_id
    ]
    assert len(executions) == 1


def test_running_self_improvement_is_grandfathered_not_migrated_mid_candidate(tmp_path: Path) -> None:
    queue, source = _source_task(tmp_path, state="running")
    github = FakeGitHub()

    report = route_self_improvement(tmp_path, requester=github.request)

    assert report["routed"] == []
    assert report["skipped_in_flight"] == [source.task_id]
    assert queue.get(source.task_id).state == "running"
    assert github.issues == []


def test_github_failure_leaves_internal_source_unassigned(tmp_path: Path) -> None:
    queue, source = _source_task(tmp_path)

    def unavailable(method: str, path: str, payload: dict | None = None):
        return None

    report = route_self_improvement(tmp_path, requester=unavailable)

    assert report["status"] == "blocked"
    assert queue.get(source.task_id).state == "new"
    executions = [
        task for task in queue.list(limit=100)
        if task.payload.get("source_self_improvement_task_id") == source.task_id
    ]
    assert executions == []


def test_proactive_plan_is_persisted_as_non_executable_source_for_next_issue_pass(tmp_path: Path) -> None:
    target = tmp_path / "genesis" / "sample.py"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("VALUE = 1\n", encoding="utf-8")

    task, created = create_planned_self_improvement_task(
        tmp_path,
        title="Improve sample reliability",
        rationale="Handle an observed edge case.",
        proposal={"files": {"genesis/sample.py": "VALUE = 2\n"}},
        development_source="file_by_file_self_review",
    )

    assert created is True
    assert task is not None
    assert task.state == "new"
    assert task.payload["task_type"] == "planned_self_improvement"
    assert task.payload["source"] == "genesis.proactive_planner"
    assert task.payload["target_path"] == "genesis/sample.py"
    assert int(task.payload.get("github_issue_number") or 0) == 0
