from __future__ import annotations

from pathlib import Path

from genesis.capability_issue_router import (
    PERFORMANCE_LABEL,
    PERFORMANCE_REASON_PREFIX,
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
        if method == "GET" and path.startswith("/issues?state=all"):
            return list(self.issues)
        if method == "GET" and path == "/issues?state=open&per_page=100":
            return [row for row in self.issues if row.get("state") == "open"]
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
                    patch = dict(payload or {})
                    if "labels" in patch:
                        patch["labels"] = [{"name": value} for value in patch["labels"]]
                    row.update(patch)
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


def test_capability_growth_becomes_closed_performance_indicator(tmp_path: Path) -> None:
    queue, source = _source_task(tmp_path)
    github = FakeGitHub()

    report = route_capability_growth(tmp_path, requester=github.request)

    assert report["status"] == "ok"
    assert report["routed"] == []
    assert len(report["indicators"]) == 1
    current = queue.get(source.task_id)
    assert current is not None
    assert current.state == "cancelled"
    assert str(current.state_reason).startswith(PERFORMANCE_REASON_PREFIX)

    assert github.labels[0]["name"] == PERFORMANCE_LABEL
    assert len(github.issues) == 1
    indicator = github.issues[0]
    assert indicator["state"] == "closed"
    assert indicator["state_reason"] == "not_planned"
    assert indicator["title"].startswith("[Performance Indicator]")
    assert indicator["labels"] == [{"name": PERFORMANCE_LABEL}]
    assert f"<!-- genesis-capability-source:{source.task_id} -->" in indicator["body"]
    assert "must not enter DevLab" in indicator["body"]


def test_indicator_routing_is_idempotent_and_creates_no_execution_task(tmp_path: Path) -> None:
    queue, source = _source_task(tmp_path)
    github = FakeGitHub()

    first = route_capability_growth(tmp_path, requester=github.request)
    second = route_capability_growth(tmp_path, requester=github.request)

    assert len(first["indicators"]) == 1
    assert len(second["indicators"]) == 1
    assert len(github.issues) == 1
    executions = [
        task
        for task in queue.list(limit=100)
        if task.payload.get("source_capability_task_id") == source.task_id
    ]
    assert executions == []


def test_running_capability_measurement_is_cancelled_not_left_in_solver_lane(tmp_path: Path) -> None:
    queue, source = _source_task(tmp_path, state="running")
    github = FakeGitHub()

    report = route_capability_growth(tmp_path, requester=github.request)

    assert report["skipped_in_flight"] == []
    current = queue.get(source.task_id)
    assert current is not None
    assert current.state == "cancelled"
    assert github.issues[0]["state"] == "closed"


def test_github_failure_still_removes_performance_measurement_from_execution_queue(tmp_path: Path) -> None:
    queue, source = _source_task(tmp_path)

    def unavailable(method: str, path: str, payload: dict | None = None):
        return None

    report = route_capability_growth(tmp_path, requester=unavailable)

    assert report["status"] == "partial"
    current = queue.get(source.task_id)
    assert current is not None
    assert current.state == "cancelled"
    assert str(current.state_reason).startswith(PERFORMANCE_REASON_PREFIX)
    assert report["routed"] == []


def test_legacy_execution_task_is_cancelled_when_source_is_reclassified(tmp_path: Path) -> None:
    queue, source = _source_task(tmp_path)
    execution, _ = queue.create_unique(
        "legacy-capability-execution",
        "Legacy benchmark repair",
        module_id="genesis.coding",
        payload={
            "task_type": "capability_growth",
            "source_capability_task_id": source.task_id,
            "github_issue_number": 336,
        },
    )
    github = FakeGitHub()

    report = route_capability_growth(tmp_path, requester=github.request)

    current_execution = queue.get(execution.task_id)
    assert current_execution is not None
    assert current_execution.state == "cancelled"
    assert report["indicators"][0]["cancelled_legacy_execution_tasks"] == [execution.task_id]


def test_legacy_backed_capability_issue_is_closed_as_performance_indicator(tmp_path: Path) -> None:
    queue = PersistentTaskQueue(tmp_path / "runtime" / "genesis_tasks.sqlite3")
    source, _ = queue.create_unique(
        "legacy-capability-source",
        "Improve measured Genesis capability gap",
        module_id="genesis.coding",
        payload={
            "source": "genesis.evolution_learning",
            "task_type": "capability_growth",
            "github_issue_number": 336,
        },
    )
    execution, _ = queue.create_unique(
        "legacy-capability-execution-336",
        "Legacy issue-backed capability execution",
        module_id="genesis.coding",
        payload={
            "task_type": "capability_growth",
            "source_capability_task_id": source.task_id,
            "github_issue_number": 336,
        },
    )
    github = FakeGitHub()
    github.issues.append(
        {
            "number": 336,
            "title": "Genesis Control: Capability Growth — software_engineering / swe_bench_pro / generation 6",
            "body": (
                f"<!-- genesis-capability-source:{source.task_id} -->\n"
                "- **Benchmark:** `swe_bench_pro`\n"
                "- **Validated baseline:** 0.0 percent\n"
                "- **Reference:** 80.3 percent\n\n"
                "### Objective\n"
                "Improve the measured Genesis capability gap for benchmark swe_bench_pro.\n"
            ),
            "labels": [{"name": "agentic-lab"}, {"name": "genesis-qwen3-agentic"}],
            "state": "open",
        }
    )

    report = route_capability_growth(tmp_path, requester=github.request)

    assert report["status"] == "ok"
    assert report["source_tasks"] == 0
    assert report["legacy_indicators"][0]["github_issue_number"] == 336
    issue = github.issues[0]
    assert issue["state"] == "closed"
    assert issue["state_reason"] == "not_planned"
    assert issue["title"].startswith("[Performance Indicator]")
    assert issue["labels"] == [{"name": PERFORMANCE_LABEL}]
    assert "<!-- genesis-performance-indicator -->" in issue["body"]
    assert queue.get(source.task_id).state == "cancelled"
    assert queue.get(execution.task_id).state == "cancelled"
