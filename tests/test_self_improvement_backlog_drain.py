from __future__ import annotations

from pathlib import Path

from genesis.modules.task_queue import PersistentTaskQueue
from genesis.self_improvement_backlog_drain import route_existing_self_improvement
from genesis.self_improvement_issue_router import ROUTER_PAUSE_PREFIX


class FakeGitHub:
    def __init__(self, issues: list[dict]) -> None:
        self.issues = list(issues)
        self.posts: list[tuple[str, str, dict | None]] = []

    def request(self, method: str, path: str, payload: dict | None = None):
        if method == "GET" and path == "/issues?state=open&labels=genesis-self-improvement&per_page=100":
            return list(self.issues)
        self.posts.append((method, path, payload))
        raise AssertionError("backlog drain must not mutate GitHub Issues")


def _source(root: Path, task_id: str = "self-improvement:competitive"):
    queue = PersistentTaskQueue(root / "runtime" / "genesis_tasks.sqlite3")
    task, _ = queue.create_unique(
        task_id,
        "Raise measured competitive AI capability with evidence.",
        module_id="genesis.capability",
        priority=100,
        payload={
            "task_type": "competitive_ai_improvement",
            "required_outcome": "Produce evidence or a bounded candidate; do not self-award score.",
        },
        max_attempts=4,
    )
    return queue, task


def test_existing_open_self_improvement_issue_is_adopted_without_new_issue(tmp_path: Path) -> None:
    queue, source = _source(tmp_path)
    github = FakeGitHub(
        [
            {
                "number": 340,
                "state": "open",
                "html_url": "https://github.test/issues/340",
                "body": f"<!-- genesis-self-improvement-source:{source.task_id} -->\n",
            }
        ]
    )

    report = route_existing_self_improvement(tmp_path, requester=github.request)

    assert report["status"] == "drain_existing_only"
    assert len(report["routed"]) == 1
    assert report["routed"][0]["github_issue_number"] == 340
    assert github.posts == []

    paused = queue.get(source.task_id)
    assert paused is not None
    assert paused.state == "paused"
    assert str(paused.state_reason).startswith(ROUTER_PAUSE_PREFIX)

    execution = queue.get(report["routed"][0]["execution_task_id"])
    assert execution is not None
    assert execution.state == "new"
    assert execution.payload["source"] == "github_self_improvement_issue"
    assert execution.payload["github_issue_number"] == 340
    assert execution.payload["task_type"] == "competitive_ai_improvement"


def test_missing_existing_issue_is_deferred_without_publishing(tmp_path: Path) -> None:
    queue, source = _source(tmp_path)
    github = FakeGitHub([])

    report = route_existing_self_improvement(tmp_path, requester=github.request)

    assert report["routed"] == []
    assert report["deferred"] == [
        {
            "source_task_id": source.task_id,
            "reason": "no_existing_open_self_improvement_issue",
        }
    ]
    assert github.posts == []
    current = queue.get(source.task_id)
    assert current is not None
    assert current.state == "new"
