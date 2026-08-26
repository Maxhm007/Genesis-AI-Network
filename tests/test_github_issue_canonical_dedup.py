from __future__ import annotations

from pathlib import Path

from genesis.github_issue_task_router import AUTONOMOUS_REPAIR_LABEL, GENESIS_TASK_LABEL, route_unbacked_tasks
from genesis.modules.task_queue import PersistentTaskQueue


class FakeGithub:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict | None]] = []
        self.issues: list[dict] = []
        self.next_issue = 100

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


def _issue_posts(github: FakeGithub) -> list[dict]:
    return [
        payload or {}
        for method, path, payload in github.calls
        if method == "POST" and path == "/issues"
    ]


def test_benchmark_retry_generations_share_one_authoritative_issue(tmp_path: Path) -> None:
    queue = _queue(tmp_path)
    base = (
        "Make benchmark swe_bench_pro executable for Genesis using the official/comparable benchmark runner and pinned dataset. "
        "Produce real raw benchmark output with provenance; never invent, estimate, hard-code or self-award a score. "
        "Integrate the smallest reproducible runner/adapter needed so BenchmarkExecutionPlanner can stage independently validated evidence. "
        "Do not embed provider credentials or lock Genesis identity to a model/provider."
    )
    first, _ = queue.create_unique(
        "benchmark-runner:swe:first",
        base,
        module_id="genesis.coding",
        payload={"task_type": "benchmark_runner_integration", "benchmark_id": "swe_bench_pro", "work_generation": 1},
    )
    second, _ = queue.create_unique(
        "benchmark-runner:swe:second",
        base
        + " This is integration generation 2. Do not repeat the previous implementation approach; use different repository evidence, adapter boundaries, or execution strategy while preserving all validation rules. Previous bounded attempt ended with: TimeoutError: timed out",
        module_id="genesis.coding",
        payload={"task_type": "benchmark_runner_integration", "benchmark_id": "swe_bench_pro", "work_generation": 2},
    )

    github = FakeGithub()
    result = route_unbacked_tasks(tmp_path, requester=github)

    assert result["status"] == "ok"
    assert len(_issue_posts(github)) == 1
    rebound_first = queue.get(first.task_id)
    rebound_second = queue.get(second.task_id)
    assert rebound_first is not None and rebound_second is not None
    assert rebound_first.payload["github_issue_number"] == rebound_second.payload["github_issue_number"] == 101
    assert rebound_first.payload["problem_fingerprint"] == rebound_second.payload["problem_fingerprint"]


def test_same_learned_idea_with_new_generated_name_reuses_issue(tmp_path: Path) -> None:
    queue = _queue(tmp_path)
    lesson = (
        "Use the learned idea: Add one new bounded Genesis capability implementing this verified transferable lesson: "
        "Reuse validated build artifacts instead of rebuilding identical outputs in each downstream job."
    )
    first, _ = queue.create_unique(
        "learned:first",
        "Autonomously add one bounded executable Genesis capability named learned_1111111111111111. " + lesson,
        module_id="genesis.coding",
        payload={
            "task_type": "new_capability",
            "source": "genesis.evolution_learning",
            "target_path": "genesis/learned_capabilities.py",
        },
    )
    second, _ = queue.create_unique(
        "learned:second",
        "Autonomously add one bounded executable Genesis capability named learned_2222222222222222. " + lesson,
        module_id="genesis.coding",
        payload={
            "task_type": "new_capability",
            "source": "genesis.evolution_learning",
            "target_path": "genesis/learned_capabilities.py",
        },
    )

    github = FakeGithub()
    route_unbacked_tasks(tmp_path, requester=github)

    assert len(_issue_posts(github)) == 1
    rebound_first = queue.get(first.task_id)
    rebound_second = queue.get(second.task_id)
    assert rebound_first is not None and rebound_second is not None
    assert rebound_first.payload["github_issue_number"] == rebound_second.payload["github_issue_number"] == 101


def test_distinct_learned_ideas_still_create_distinct_issues(tmp_path: Path) -> None:
    queue = _queue(tmp_path)
    for index, lesson in enumerate(("cache immutable build artifacts", "validate JSON before persistence"), start=1):
        queue.create_unique(
            f"learned:{index}",
            f"Autonomously add one bounded executable Genesis capability named learned_{index:016x}. Use the learned idea: {lesson}.",
            module_id="genesis.coding",
            payload={
                "task_type": "new_capability",
                "source": "genesis.evolution_learning",
                "target_path": "genesis/learned_capabilities.py",
            },
        )

    github = FakeGithub()
    route_unbacked_tasks(tmp_path, requester=github)

    assert len(_issue_posts(github)) == 2
