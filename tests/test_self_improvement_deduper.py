from __future__ import annotations

from pathlib import Path

from genesis.modules.task_queue import PersistentTaskQueue
from genesis.self_improvement_deduper import dedupe_self_improvement, problem_fingerprint
from genesis.self_improvement_issue_router import ROUTER_PAUSE_PREFIX, route_self_improvement


class FakeGitHub:
    def __init__(self) -> None:
        self.labels: list[dict] = []
        self.issues: list[dict] = []
        self.next_issue = 801

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


def _source(queue: PersistentTaskQueue, key: str):
    return queue.create_unique(
        key,
        "Increase Gene's validated development velocity without weakening tests, security, provenance, independent validator quorum, owner authorization, or Constitution constraints.",
        module_id="genesis.capability",
        priority=100,
        payload={
            "task_type": "gene_velocity_improvement",
            "required_outcome": "Reduce validated development latency while preserving safety gates.",
        },
        max_attempts=4,
    )[0]


def _execution(queue: PersistentTaskQueue, source_task_id: str, issue_number: int):
    return queue.create_unique(
        f"execution:{issue_number}:{source_task_id}",
        f"Process self-improvement issue #{issue_number}.",
        module_id="genesis.capability",
        priority=100,
        payload={
            "task_type": "gene_velocity_improvement",
            "source": "github_self_improvement_issue",
            "execution_lane": "github_issue",
            "github_issue_number": issue_number,
            "github_issue_url": f"https://github.test/issues/{issue_number}",
            "source_self_improvement_task_id": source_task_id,
        },
        max_attempts=4,
    )[0]


def test_same_problem_from_two_source_tasks_creates_one_issue(tmp_path: Path) -> None:
    queue = PersistentTaskQueue(tmp_path / "runtime" / "genesis_tasks.sqlite3")
    first = _source(queue, "velocity-detection:first")
    second = _source(queue, "velocity-detection:second")
    github = FakeGitHub()

    assert problem_fingerprint(first) == problem_fingerprint(second)

    dedupe = dedupe_self_improvement(tmp_path)
    routed = route_self_improvement(tmp_path, requester=github.request)

    assert dedupe["duplicate_groups"] == 1
    assert len(dedupe["cancelled_sources"]) == 1
    assert queue.get(first.task_id).state != "cancelled"
    assert queue.get(second.task_id).state == "cancelled"
    assert len(routed["routed"]) == 1
    assert len(github.issues) == 1


def test_existing_duplicate_issue_execution_is_cancelled_before_routing(tmp_path: Path) -> None:
    queue = PersistentTaskQueue(tmp_path / "runtime" / "genesis_tasks.sqlite3")
    first = _source(queue, "velocity-existing:first")
    second = _source(queue, "velocity-existing:second")
    first = queue.pause(first.task_id, f"{ROUTER_PAUSE_PREFIX}341: authoritative issue lane")
    second = queue.pause(second.task_id, f"{ROUTER_PAUSE_PREFIX}342: authoritative issue lane")
    first_execution = _execution(queue, first.task_id, 341)
    second_execution = _execution(queue, second.task_id, 342)

    report = dedupe_self_improvement(tmp_path)

    assert report["duplicate_groups"] == 1
    assert queue.get(first.task_id).state == "paused"
    assert queue.get(first_execution.task_id).state == "new"
    assert queue.get(second.task_id).state == "cancelled"
    assert queue.get(second_execution.task_id).state == "cancelled"
    assert report["cancelled_execution_tasks"][0]["github_issue_number"] == 342
