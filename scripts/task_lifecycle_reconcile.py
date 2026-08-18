from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import subprocess

from genesis.modules.task_queue import PersistentTaskQueue


ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "runtime"
STALE_REVIEW_HOURS = 3


def _parse_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _is_ancestor(commit_sha: str) -> bool:
    if not commit_sha:
        return False
    proc = subprocess.run(
        ["git", "merge-base", "--is-ancestor", commit_sha, "HEAD"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    return proc.returncode == 0


def _candidate_evidence() -> dict[str, str]:
    path = RUNTIME / "autonomous_engineering.json"
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


def reconcile() -> dict:
    queue = PersistentTaskQueue(RUNTIME / "genesis_tasks.sqlite3")
    evidence = _candidate_evidence()
    now = datetime.now(timezone.utc)
    completed: list[str] = []
    retried: list[str] = []
    waiting: list[str] = []

    for task in queue.list(state="review", limit=1000):
        commit_sha = evidence.get(task.task_id, "")
        if commit_sha and _is_ancestor(commit_sha):
            queue.transition(task.task_id, "complete", module_id=task.module_id)
            completed.append(task.task_id)
            continue

        age = now - _parse_time(task.updated_at)
        if age >= timedelta(hours=STALE_REVIEW_HOURS):
            updated = queue.record_failure(
                task.task_id,
                "review candidate was not observed on main within bounded review window",
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
        "review_count": len(completed) + len(retried) + len(waiting),
    }
    (RUNTIME / "task_lifecycle_reconcile.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(result, sort_keys=True))
    return result


if __name__ == "__main__":
    reconcile()
