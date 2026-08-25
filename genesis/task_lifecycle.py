from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import subprocess

from .modules.task_queue import PersistentTaskQueue


REVIEW_ARTIFACT_TASK_TYPES = {
    "immortality_research",
    "competitive_ai_improvement",
    "competitive_reference_refresh",
}

BOUNDED_BLOCKED_TASK_TYPES = {
    "operational_issue",
    "benchmark_runner_integration",
    "github_issue_development",
}


class TaskLifecycleReconciler:
    """Close promoted reviews and recover bounded autonomous work safely.

    Review-state work is reconciled against durable completion evidence. Autonomous
    implementation tasks that remain blocked are counted as failed attempts instead
    of being retried forever without consuming their configured retry budget. A
    retryable failure is immediately reassigned for the next engineering pass; once
    the budget is exhausted the task is quarantined so an owning planner may create
    a fresh work generation rather than looping on the same failed attempt.
    """

    STALE_REVIEW_HOURS = 3

    def __init__(self, root: Path) -> None:
        self.root = Path(root).resolve()
        self.runtime = self.root / "runtime"
        self.runtime.mkdir(parents=True, exist_ok=True)
        self.queue = PersistentTaskQueue(self.runtime / "genesis_tasks.sqlite3")

    @staticmethod
    def _parse_time(value: str) -> datetime:
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

    def _is_ancestor(self, commit_sha: str) -> bool:
        if not commit_sha:
            return False
        proc = subprocess.run(
            ["git", "merge-base", "--is-ancestor", commit_sha, "HEAD"],
            cwd=self.root,
            capture_output=True,
            text=True,
            check=False,
        )
        return proc.returncode == 0

    def _candidate_evidence(self) -> dict[str, str]:
        path = self.runtime / "autonomous_engineering.json"
        if not path.exists():
            return {}
        try:
            report = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {}
        result: dict[str, str] = {}
        for attempt in report.get("attempted_tasks", []):
            task = attempt.get("task") if isinstance(attempt, dict) else None
            candidate = attempt.get("candidate") if isinstance(attempt, dict) else None
            if not isinstance(task, dict) or not isinstance(candidate, dict):
                continue
            task_id = str(task.get("task_id", ""))
            commit_sha = str(candidate.get("commit_sha") or "")
            if task_id and commit_sha:
                result[task_id] = commit_sha
        return result

    def _has_completed_review_artifact(self, task) -> bool:
        task_type = str(task.payload.get("task_type", ""))
        if task_type not in REVIEW_ARTIFACT_TASK_TYPES:
            return False
        path = self.runtime / "task_reviews" / f"{task.task_id}.json"
        if not path.is_file():
            return False
        try:
            review = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return False
        return review.get("status") == "candidate_review"

    def _reconcile_blocked(self) -> tuple[list[str], list[str]]:
        retried: list[str] = []
        quarantined: list[str] = []
        for task in self.queue.list(state="blocked", limit=1000):
            task_type = str(task.payload.get("task_type", ""))
            if task_type not in BOUNDED_BLOCKED_TASK_TYPES:
                continue
            reason = task.state_reason or task.last_error or "autonomous implementation attempt remained blocked"
            updated = self.queue.record_failure(
                task.task_id,
                reason,
                classification="blocked_autonomous_repair",
                retry_after_seconds=0,
                module_id=task.module_id,
            )
            if updated.state == "failed" and self.queue.retryable(updated):
                self.queue.transition(updated.task_id, "assigned", module_id=updated.module_id)
                retried.append(updated.task_id)
            elif updated.state == "quarantined":
                quarantined.append(updated.task_id)
        return retried, quarantined

    def reconcile(self) -> dict:
        evidence = self._candidate_evidence()
        now = datetime.now(timezone.utc)
        completed: list[str] = []
        retried: list[str] = []
        waiting: list[str] = []
        blocked_retried, blocked_quarantined = self._reconcile_blocked()

        for task in self.queue.list(state="review", limit=1000):
            if self._has_completed_review_artifact(task):
                self.queue.transition(task.task_id, "complete", module_id=task.module_id)
                completed.append(task.task_id)
                continue

            commit_sha = evidence.get(task.task_id, "")
            if commit_sha and self._is_ancestor(commit_sha):
                self.queue.transition(task.task_id, "complete", module_id=task.module_id)
                completed.append(task.task_id)
                continue

            age = now - self._parse_time(task.updated_at)
            if age >= timedelta(hours=self.STALE_REVIEW_HOURS):
                updated = self.queue.record_failure(
                    task.task_id,
                    "review candidate was not observed as completed within bounded review window",
                    classification="stale_review",
                    retry_after_seconds=0,
                    module_id=task.module_id,
                )
                retried.append(updated.task_id)
            else:
                waiting.append(task.task_id)

        result = {
            "status": "ok",
            "completed": completed,
            "retried": retried,
            "waiting": waiting,
            "blocked_retried": blocked_retried,
            "blocked_quarantined": blocked_quarantined,
            "review_count": len(completed) + len(retried) + len(waiting),
        }
        (self.runtime / "task_lifecycle_reconcile.json").write_text(
            json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        return result
