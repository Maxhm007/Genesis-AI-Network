from __future__ import annotations

from pathlib import Path

import genesis.research_tasks as research_tasks
from genesis.modules.task_queue import PersistentTaskQueue
from genesis.specialist_issue_completion import publish_specialist_completion_evidence


class FakeGithub:
    def __init__(self, *, fail_comment: bool = False) -> None:
        self.issue = {
            "number": 340,
            "title": "[Genesis Self Improvement] competitive ai improvement",
            "state": "open",
            "labels": [{"name": "genesis-task"}, {"name": "genesis-self-improvement"}],
        }
        self.comments: list[dict] = []
        self.fail_comment = fail_comment
        self.calls: list[tuple[str, str, dict | None]] = []

    def __call__(self, method: str, path: str, payload: dict | None = None):
        self.calls.append((method, path, payload))
        if method == "GET" and path == "/issues/340":
            return dict(self.issue)
        if method == "GET" and path == "/issues/340/comments?per_page=100":
            return list(self.comments)
        if method == "POST" and path == "/issues/340/comments":
            if self.fail_comment:
                return None
            row = {"id": len(self.comments) + 1, "body": str((payload or {}).get("body") or "")}
            self.comments.append(row)
            return dict(row)
        raise AssertionError((method, path, payload))


def _review_task(root: Path):
    queue = PersistentTaskQueue(root / "runtime" / "genesis_tasks.sqlite3")
    task, _ = queue.create_unique(
        "specialist-340",
        "Measure the weakest competitive benchmark dimension with bounded evidence.",
        module_id="genesis.capability",
        priority=100,
        payload={"task_type": "competitive_ai_improvement", "github_issue_number": 340},
    )
    task = queue.transition(task.task_id, "assigned", module_id="genesis.capability")
    task = queue.transition(task.task_id, "running", module_id="genesis.capability")
    task = queue.transition(task.task_id, "review", module_id="genesis.capability")
    return queue, task


def test_specialist_completion_evidence_is_bounded_and_idempotent(tmp_path: Path) -> None:
    _, task = _review_task(tmp_path)
    review_path = tmp_path / "runtime" / "task_reviews" / f"{task.task_id}.json"
    review_path.parent.mkdir(parents=True, exist_ok=True)
    review_path.write_text('{"status":"candidate_review"}\n', encoding="utf-8")
    github = FakeGithub()

    first = publish_specialist_completion_evidence(
        tmp_path,
        task,
        review_path=review_path,
        team_members=["Gene 0", "Gene 2", "Gene 3"],
        requester=github,
    )
    second = publish_specialist_completion_evidence(
        tmp_path,
        task,
        review_path=review_path,
        team_members=["Gene 0", "Gene 2", "Gene 3"],
        requester=github,
    )

    assert first["status"] == "reported"
    assert first["reported"] is True
    assert second["status"] == "already_reported"
    assert second["reported"] is True
    assert len(github.comments) == 1
    body = github.comments[0]["body"]
    assert f"genesis-specialist-completion:{task.task_id}" in body
    assert "candidate/review evidence only" in body.lower()
    assert "does not self-award a benchmark score" in body


def test_specialist_comment_failure_does_not_report_completion(tmp_path: Path) -> None:
    _, task = _review_task(tmp_path)
    review_path = tmp_path / "runtime" / "task_reviews" / f"{task.task_id}.json"
    review_path.parent.mkdir(parents=True, exist_ok=True)
    review_path.write_text('{"status":"candidate_review"}\n', encoding="utf-8")
    github = FakeGithub(fail_comment=True)

    result = publish_specialist_completion_evidence(
        tmp_path,
        task,
        review_path=review_path,
        team_members=["Gene 0"],
        requester=github,
    )

    assert result["status"] == "blocked"
    assert result["reported"] is False
    assert result["reason"] == "github_completion_evidence_comment_failed"


class FakeTeam:
    def __init__(self) -> None:
        self.calls = 0

    def run_task(self, objective: str, *, context: str):
        self.calls += 1
        return [
            {"agent": "Gene 0", "output": "candidate evidence"},
            {"agent": "Gene 2", "output": "review"},
            {"agent": "Gene 3", "output": "independent critique"},
        ]


def _worker_task(
    worker: research_tasks.ImmortalityResearchWorker,
    *,
    issue_number: int = 340,
    fingerprint: str | None = None,
):
    payload = {"task_type": "competitive_ai_improvement"}
    if issue_number:
        payload["github_issue_number"] = issue_number
    task, _ = worker.queue.create_unique(
        fingerprint or f"worker-specialist-{issue_number}",
        "Measure frontier competitive benchmark evidence without self-awarding a score.",
        module_id="genesis.capability",
        priority=100,
        payload=payload,
    )
    return task


def test_worker_posts_evidence_then_completes_and_closes_issue(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(research_tasks, "issue_authority_enabled", lambda root: True)
    monkeypatch.setattr(research_tasks, "route_unbacked_tasks", lambda root: {"status": "ok"})
    evidence_calls = []

    def fake_publish(root, task, *, review_path, team_members):
        evidence_calls.append((task.state, review_path.exists(), list(team_members)))
        return {"status": "reported", "reported": True, "github_issue_number": 340}

    monkeypatch.setattr(research_tasks, "publish_specialist_completion_evidence", fake_publish)
    monkeypatch.setattr(
        research_tasks,
        "reconcile_terminal_github_issues",
        lambda root: {"status": "ok", "closed": [{"github_issue_number": 340}], "already_closed": []},
    )
    worker = research_tasks.ImmortalityResearchWorker(tmp_path)
    worker.team = FakeTeam()
    task = _worker_task(worker)

    result = worker.run_one()

    assert evidence_calls == [("review", True, ["Gene 0", "Gene 2", "Gene 3"])]
    assert worker.team.calls == 1
    assert worker.queue.get(task.task_id).state == "complete"
    assert result["status"] == "review_completed"
    assert result["github_issue_reconciled"] is True


def test_worker_leaves_task_in_review_when_github_evidence_fails(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(research_tasks, "issue_authority_enabled", lambda root: True)
    monkeypatch.setattr(research_tasks, "route_unbacked_tasks", lambda root: {"status": "ok"})
    monkeypatch.setattr(
        research_tasks,
        "publish_specialist_completion_evidence",
        lambda *args, **kwargs: {
            "status": "blocked",
            "reported": False,
            "reason": "github_completion_evidence_comment_failed",
        },
    )

    def must_not_close(root):
        raise AssertionError("terminal reconciliation must not run before evidence is attached")

    monkeypatch.setattr(research_tasks, "reconcile_terminal_github_issues", must_not_close)
    worker = research_tasks.ImmortalityResearchWorker(tmp_path)
    worker.team = FakeTeam()
    task = _worker_task(worker)

    result = worker.run_one()

    assert worker.team.calls == 1
    assert worker.queue.get(task.task_id).state == "review"
    assert result["status"] == "github_issue_reconciliation_pending"
    assert result["github_issue_reconciled"] is False


def test_worker_retries_review_reconciliation_without_rerunning_research(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(research_tasks, "issue_authority_enabled", lambda root: True)
    monkeypatch.setattr(research_tasks, "route_unbacked_tasks", lambda root: {"status": "ok"})
    evidence_attempts = {"count": 0}

    def fake_publish(root, task, *, review_path, team_members):
        evidence_attempts["count"] += 1
        if evidence_attempts["count"] == 1:
            return {
                "status": "blocked",
                "reported": False,
                "reason": "github_completion_evidence_comment_failed",
            }
        return {"status": "reported", "reported": True, "github_issue_number": 340}

    monkeypatch.setattr(research_tasks, "publish_specialist_completion_evidence", fake_publish)
    monkeypatch.setattr(
        research_tasks,
        "reconcile_terminal_github_issues",
        lambda root: {"status": "ok", "closed": [{"github_issue_number": 340}], "already_closed": []},
    )
    worker = research_tasks.ImmortalityResearchWorker(tmp_path)
    worker.team = FakeTeam()
    task = _worker_task(worker)

    first = worker.run_one()
    second = worker.run_one()

    assert first["status"] == "github_issue_reconciliation_pending"
    assert first["research_reexecuted"] is True
    assert second["status"] == "review_completed"
    assert second["research_reexecuted"] is False
    assert worker.team.calls == 1
    assert evidence_attempts["count"] == 2
    assert worker.queue.get(task.task_id).state == "complete"


def test_reconciled_completed_task_does_not_starve_new_specialist_work(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(research_tasks, "issue_authority_enabled", lambda root: True)
    monkeypatch.setattr(research_tasks, "route_unbacked_tasks", lambda root: {"status": "ok"})
    closed_issues = {340}

    def fake_reconcile(root):
        return {
            "status": "ok",
            "closed": [],
            "already_closed": sorted(closed_issues),
        }

    def fake_publish(root, task, *, review_path, team_members):
        issue_number = int(task.payload.get("github_issue_number") or 0)
        closed_issues.add(issue_number)
        return {"status": "reported", "reported": True, "github_issue_number": issue_number}

    monkeypatch.setattr(research_tasks, "reconcile_terminal_github_issues", fake_reconcile)
    monkeypatch.setattr(research_tasks, "publish_specialist_completion_evidence", fake_publish)
    worker = research_tasks.ImmortalityResearchWorker(tmp_path)
    worker.team = FakeTeam()

    completed = _worker_task(worker, issue_number=340, fingerprint="completed-340")
    worker.queue.transition(completed.task_id, "assigned", module_id="genesis.capability")
    worker.queue.transition(completed.task_id, "running", module_id="genesis.capability")
    worker.queue.transition(completed.task_id, "review", module_id="genesis.capability")
    worker.queue.transition(completed.task_id, "complete", module_id="genesis.capability")
    fresh = _worker_task(worker, issue_number=341, fingerprint="fresh-341")

    result = worker.run_one()

    assert result["task_id"] == fresh.task_id
    assert result["github_issue_number"] == 341
    assert worker.team.calls == 1
    assert worker.queue.get(fresh.task_id).state == "complete"


def test_worker_without_issue_authority_completes_without_github_mutation(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(research_tasks, "issue_authority_enabled", lambda root: False)
    monkeypatch.setattr(research_tasks, "route_unbacked_tasks", lambda root: {"status": "not_repository_runtime"})

    def must_not_publish(*args, **kwargs):
        raise AssertionError("local non-authoritative work must not mutate GitHub")

    monkeypatch.setattr(research_tasks, "publish_specialist_completion_evidence", must_not_publish)
    monkeypatch.setattr(research_tasks, "reconcile_terminal_github_issues", lambda root: (_ for _ in ()).throw(AssertionError("must not close")))
    worker = research_tasks.ImmortalityResearchWorker(tmp_path)
    worker.team = FakeTeam()
    task = _worker_task(worker, issue_number=0)

    result = worker.run_one()

    assert worker.team.calls == 1
    assert worker.queue.get(task.task_id).state == "complete"
    assert result["status"] == "review_completed"
    assert result["github_issue_number"] == 0
    assert result["github_issue_reconciled"] is False
