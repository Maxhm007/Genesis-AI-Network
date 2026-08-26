from __future__ import annotations

from pathlib import Path

from genesis.capability_issue_router import (
    CAPABILITY_LABEL,
    ROUTER_PAUSE_PREFIX,
    route_capability_growth,
)
from genesis.modules.task_queue import PersistentTaskQueue


class FakeGitHub:
    def __init__(self) -> None:
        self.labels: list[dict] = []
        self.issues: list[dict] = []
        self.next_issue = 501

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


def _source_task(root: Path, *, state: str = "new"):
    target = root / "genesis" / "coding.py"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("VALUE = 1\n", encoding="utf-8")
    queue = PersistentTaskQueue(root / "runtime" / "genesis_tasks.sqlite3")
    task, _ = queue.create_unique(
        "capability-growth:swe_bench_pro:generation:1",
        "Improve measured software engineering capability without hard-coding benchmark answers.",
        module_id="genesis.coding",
        priority=95,
        payload={
            "source": "genesis.evolution_learning",
            "task_type": "capability_growth",
            "target_path": "genesis/coding.py",
            "context_paths": ["genesis/coding.py"],
            "capability_key": "software_engineering",
            "capability_generation": 1,
            "benchmark_gap": {
                "benchmark_id": "swe_bench_pro",
                "capability_key": "software_engineering",
                "growth_generation": 1,
                "reference_score": 80.0,
                "unit": "percent",
            },
            "baseline_score": 32.0,
            "discovery": {
                "finding": {
                    "acceptance": "Pass tests and validators, then remeasure the same benchmark for real gain."
                }
            },
            "requires_independent_validation": True,
            "score_fabrication_forbidden": True,
        },
        max_attempts=4,
    )
    if state == "assigned":
        task = queue.transition(task.task_id, "assigned", module_id="genesis.coding")
    elif state == "running":
        task = queue.transition(task.task_id, "assigned", module_id="genesis.coding")
        task = queue.transition(task.task_id, "running", module_id="genesis.coding")
    return queue, task


def test_capability_growth_is_cut_over_to_one_issue_backed_devlab_task(tmp_path: Path) -> None:
    queue, source = _source_task(tmp_path)
    github = FakeGitHub()

    report = route_capability_growth(tmp_path, requester=github.request)

    assert report["status"] == "ok"
    assert len(report["routed"]) == 1
    paused = queue.get(source.task_id)
    assert paused is not None
    assert paused.state == "paused"
    assert str(paused.state_reason).startswith(ROUTER_PAUSE_PREFIX)

    routed = report["routed"][0]
    execution = queue.get(routed["execution_task_id"])
    assert execution is not None
    assert execution.payload["task_type"] == "capability_growth"
    assert execution.payload["executor"] == "genesis.devlab"
    assert execution.payload["execution_lane"] == "github_issue"
    assert execution.payload["source_capability_task_id"] == source.task_id
    assert execution.payload["github_issue_number"] == 501
    assert execution.payload["close_github_issue_after_promotion"] is True
    assert execution.payload["requires_independent_validation"] is True
    assert execution.payload["score_fabrication_forbidden"] is True

    assert github.labels[0]["name"] == CAPABILITY_LABEL
    assert github.issues[0]["title"].startswith("Genesis Control: Capability Growth")
    assert f"<!-- genesis-capability-source:{source.task_id} -->" in github.issues[0]["body"]
    assert "authoritative execution lane" in github.issues[0]["body"]


def test_capability_issue_routing_is_idempotent_and_never_creates_second_execution_task(tmp_path: Path) -> None:
    queue, source = _source_task(tmp_path)
    github = FakeGitHub()

    first = route_capability_growth(tmp_path, requester=github.request)
    second = route_capability_growth(tmp_path, requester=github.request)

    assert len(first["routed"]) == 1
    assert second["routed"] == []
    assert len(second["already_routed"]) == 1
    assert len(github.issues) == 1
    executions = [
        task
        for task in queue.list(limit=100)
        if task.payload.get("source_capability_task_id") == source.task_id
    ]
    assert len(executions) == 1


def test_in_flight_legacy_capability_work_is_not_migrated_mid_candidate(tmp_path: Path) -> None:
    queue, source = _source_task(tmp_path, state="running")
    github = FakeGitHub()

    report = route_capability_growth(tmp_path, requester=github.request)

    assert report["routed"] == []
    assert report["skipped_in_flight"] == [source.task_id]
    current = queue.get(source.task_id)
    assert current is not None
    assert current.state == "running"
    assert github.issues == []


def test_github_failure_leaves_source_capability_task_executable(tmp_path: Path) -> None:
    queue, source = _source_task(tmp_path)

    def unavailable(method: str, path: str, payload: dict | None = None):
        return None

    report = route_capability_growth(tmp_path, requester=unavailable)

    assert report["status"] == "blocked"
    current = queue.get(source.task_id)
    assert current is not None
    assert current.state == "new"
    executions = [
        task
        for task in queue.list(limit=100)
        if task.payload.get("source_capability_task_id") == source.task_id
    ]
    assert executions == []
