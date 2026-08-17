from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
import hashlib
import json
import sqlite3
import uuid


VALID_STATES = {"new", "assigned", "running", "blocked", "review", "complete", "failed", "quarantined"}
VALID_TRANSITIONS = {
    "new": {"assigned", "blocked", "failed"},
    "assigned": {"running", "blocked", "failed"},
    "running": {"review", "blocked", "failed"},
    "blocked": {"assigned", "running", "failed"},
    "review": {"complete", "running", "failed"},
    "complete": set(),
    "failed": {"assigned", "quarantined"},
    "quarantined": {"assigned"},
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_utc(value: str | None) -> datetime | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


@dataclass(frozen=True)
class GenesisTask:
    task_id: str
    objective: str
    module_id: str | None
    state: str
    priority: int
    payload: dict
    created_at: str
    updated_at: str
    attempt_count: int = 0
    max_attempts: int = 3
    next_retry_at: str | None = None
    last_error: str | None = None
    failure_history: tuple[dict, ...] = ()


class PersistentTaskQueue:
    """SQLite-backed task queue so Genesis can resume and recover work after restarts."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

    def _init_db(self) -> None:
        with self._connect() as db:
            db.execute(
                """
                CREATE TABLE IF NOT EXISTS genesis_tasks (
                    task_id TEXT PRIMARY KEY,
                    objective TEXT NOT NULL,
                    module_id TEXT,
                    state TEXT NOT NULL,
                    priority INTEGER NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    attempt_count INTEGER NOT NULL DEFAULT 0,
                    max_attempts INTEGER NOT NULL DEFAULT 3,
                    next_retry_at TEXT,
                    last_error TEXT,
                    failure_history_json TEXT NOT NULL DEFAULT '[]'
                )
                """
            )
            columns = {row["name"] for row in db.execute("PRAGMA table_info(genesis_tasks)").fetchall()}
            migrations = {
                "attempt_count": "ALTER TABLE genesis_tasks ADD COLUMN attempt_count INTEGER NOT NULL DEFAULT 0",
                "max_attempts": "ALTER TABLE genesis_tasks ADD COLUMN max_attempts INTEGER NOT NULL DEFAULT 3",
                "next_retry_at": "ALTER TABLE genesis_tasks ADD COLUMN next_retry_at TEXT",
                "last_error": "ALTER TABLE genesis_tasks ADD COLUMN last_error TEXT",
                "failure_history_json": "ALTER TABLE genesis_tasks ADD COLUMN failure_history_json TEXT NOT NULL DEFAULT '[]'",
            }
            for column, statement in migrations.items():
                if column not in columns:
                    db.execute(statement)

    def _insert(self, task: GenesisTask) -> GenesisTask:
        with self._connect() as db:
            db.execute(
                """
                INSERT INTO genesis_tasks (
                    task_id, objective, module_id, state, priority, payload_json,
                    created_at, updated_at, attempt_count, max_attempts,
                    next_retry_at, last_error, failure_history_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    task.task_id,
                    task.objective,
                    task.module_id,
                    task.state,
                    task.priority,
                    json.dumps(task.payload, sort_keys=True),
                    task.created_at,
                    task.updated_at,
                    task.attempt_count,
                    task.max_attempts,
                    task.next_retry_at,
                    task.last_error,
                    json.dumps(list(task.failure_history), sort_keys=True),
                ),
            )
        return task

    def create(
        self,
        objective: str,
        *,
        module_id: str | None = None,
        priority: int = 50,
        payload: dict | None = None,
        max_attempts: int = 3,
    ) -> GenesisTask:
        objective = objective.strip()
        if not objective:
            raise ValueError("objective is required")
        if priority < 0 or priority > 100:
            raise ValueError("priority must be between 0 and 100")
        if max_attempts < 1 or max_attempts > 20:
            raise ValueError("max_attempts must be between 1 and 20")
        now = utc_now()
        return self._insert(GenesisTask(
            task_id="task-" + uuid.uuid4().hex[:16],
            objective=objective,
            module_id=module_id,
            state="new",
            priority=priority,
            payload=dict(payload or {}),
            created_at=now,
            updated_at=now,
            max_attempts=max_attempts,
        ))

    def create_unique(
        self,
        dedupe_key: str,
        objective: str,
        *,
        module_id: str | None = None,
        priority: int = 50,
        payload: dict | None = None,
        max_attempts: int = 3,
    ) -> tuple[GenesisTask, bool]:
        """Create a deterministic task once, returning (task, created)."""
        dedupe_key = dedupe_key.strip()
        if not dedupe_key:
            raise ValueError("dedupe_key is required")
        objective = objective.strip()
        if not objective:
            raise ValueError("objective is required")
        if priority < 0 or priority > 100:
            raise ValueError("priority must be between 0 and 100")
        if max_attempts < 1 or max_attempts > 20:
            raise ValueError("max_attempts must be between 1 and 20")
        task_id = "task-" + hashlib.sha256(dedupe_key.encode("utf-8")).hexdigest()[:16]
        existing = self.get(task_id)
        if existing is not None:
            return existing, False
        now = utc_now()
        task_payload = dict(payload or {})
        task_payload.setdefault("dedupe_key", dedupe_key)
        task = GenesisTask(
            task_id,
            objective,
            module_id,
            "new",
            priority,
            task_payload,
            now,
            now,
            max_attempts=max_attempts,
        )
        try:
            return self._insert(task), True
        except sqlite3.IntegrityError:
            existing = self.get(task_id)
            if existing is None:
                raise
            return existing, False

    def get(self, task_id: str) -> GenesisTask | None:
        with self._connect() as db:
            row = db.execute("SELECT * FROM genesis_tasks WHERE task_id = ?", (task_id,)).fetchone()
        return self._from_row(row) if row else None

    def list(self, *, state: str | None = None, limit: int = 100) -> list[GenesisTask]:
        if state is not None and state not in VALID_STATES:
            raise ValueError("invalid task state")
        query = "SELECT * FROM genesis_tasks"
        params: list[object] = []
        if state is not None:
            query += " WHERE state = ?"
            params.append(state)
        query += " ORDER BY priority DESC, created_at ASC LIMIT ?"
        params.append(limit)
        with self._connect() as db:
            rows = db.execute(query, params).fetchall()
        return [self._from_row(row) for row in rows]

    def transition(self, task_id: str, new_state: str, *, module_id: str | None = None) -> GenesisTask:
        if new_state not in VALID_STATES:
            raise ValueError("invalid task state")
        current = self.get(task_id)
        if current is None:
            raise KeyError(task_id)
        if new_state not in VALID_TRANSITIONS[current.state]:
            raise ValueError(f"invalid transition: {current.state} -> {new_state}")
        assigned_module = module_id if module_id is not None else current.module_id
        now = utc_now()
        next_retry_at = None if new_state == "assigned" else current.next_retry_at
        with self._connect() as db:
            db.execute(
                "UPDATE genesis_tasks SET state = ?, module_id = ?, updated_at = ?, next_retry_at = ? WHERE task_id = ?",
                (new_state, assigned_module, now, next_retry_at, task_id),
            )
        updated = self.get(task_id)
        assert updated is not None
        return updated

    def record_failure(
        self,
        task_id: str,
        error: str,
        *,
        classification: str = "unknown",
        retry_after_seconds: int | None = None,
        module_id: str | None = None,
    ) -> GenesisTask:
        """Persist a failure and schedule bounded recovery or quarantine it.

        The attempt count is incremented for every recorded execution failure.
        When max_attempts is reached the task is quarantined instead of being
        retried forever. Failure history remains durable across restarts.
        """
        current = self.get(task_id)
        if current is None:
            raise KeyError(task_id)
        if current.state in {"complete", "quarantined"}:
            raise ValueError(f"cannot record failure from state {current.state}")
        error = error.strip() or "unspecified failure"
        classification = classification.strip() or "unknown"
        attempts = current.attempt_count + 1
        now_dt = datetime.now(timezone.utc)
        now = now_dt.isoformat()
        history = list(current.failure_history)
        history.append({
            "attempt": attempts,
            "at": now,
            "classification": classification,
            "error": error,
            "module_id": module_id if module_id is not None else current.module_id,
        })
        if attempts >= current.max_attempts:
            new_state = "quarantined"
            next_retry_at = None
        else:
            new_state = "failed"
            delay = retry_after_seconds
            if delay is None:
                delay = min(3600, 60 * (2 ** (attempts - 1)))
            if delay < 0:
                raise ValueError("retry_after_seconds must be non-negative")
            next_retry_at = (now_dt + timedelta(seconds=delay)).isoformat()
        assigned_module = module_id if module_id is not None else current.module_id
        with self._connect() as db:
            db.execute(
                """
                UPDATE genesis_tasks
                SET state = ?, module_id = ?, updated_at = ?, attempt_count = ?,
                    next_retry_at = ?, last_error = ?, failure_history_json = ?
                WHERE task_id = ?
                """,
                (
                    new_state,
                    assigned_module,
                    now,
                    attempts,
                    next_retry_at,
                    error,
                    json.dumps(history, sort_keys=True),
                    task_id,
                ),
            )
        updated = self.get(task_id)
        assert updated is not None
        return updated

    def retryable(self, task: GenesisTask, *, at: datetime | None = None) -> bool:
        if task.state != "failed" or task.attempt_count >= task.max_attempts:
            return False
        when = at or datetime.now(timezone.utc)
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
        retry_at = _parse_utc(task.next_retry_at)
        return retry_at is None or retry_at <= when.astimezone(timezone.utc)

    @staticmethod
    def _from_row(row: sqlite3.Row) -> GenesisTask:
        history_raw = row["failure_history_json"] if "failure_history_json" in row.keys() else "[]"
        return GenesisTask(
            task_id=row["task_id"],
            objective=row["objective"],
            module_id=row["module_id"],
            state=row["state"],
            priority=row["priority"],
            payload=json.loads(row["payload_json"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            attempt_count=row["attempt_count"] if "attempt_count" in row.keys() else 0,
            max_attempts=row["max_attempts"] if "max_attempts" in row.keys() else 3,
            next_retry_at=row["next_retry_at"] if "next_retry_at" in row.keys() else None,
            last_error=row["last_error"] if "last_error" in row.keys() else None,
            failure_history=tuple(json.loads(history_raw or "[]")),
        )
