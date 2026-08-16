from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import sqlite3
import uuid


VALID_STATES = {"new", "assigned", "running", "blocked", "review", "complete", "failed"}
VALID_TRANSITIONS = {
    "new": {"assigned", "blocked", "failed"},
    "assigned": {"running", "blocked", "failed"},
    "running": {"review", "blocked", "failed"},
    "blocked": {"assigned", "running", "failed"},
    "review": {"complete", "running", "failed"},
    "complete": set(),
    "failed": {"assigned"},
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


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


class PersistentTaskQueue:
    """SQLite-backed task queue so Genesis can resume work after restarts."""

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
                    updated_at TEXT NOT NULL
                )
                """
            )

    def _insert(self, task: GenesisTask) -> GenesisTask:
        with self._connect() as db:
            db.execute(
                "INSERT INTO genesis_tasks VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    task.task_id,
                    task.objective,
                    task.module_id,
                    task.state,
                    task.priority,
                    json.dumps(task.payload, sort_keys=True),
                    task.created_at,
                    task.updated_at,
                ),
            )
        return task

    def create(self, objective: str, *, module_id: str | None = None, priority: int = 50, payload: dict | None = None) -> GenesisTask:
        objective = objective.strip()
        if not objective:
            raise ValueError("objective is required")
        if priority < 0 or priority > 100:
            raise ValueError("priority must be between 0 and 100")
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
        ))

    def create_unique(self, dedupe_key: str, objective: str, *, module_id: str | None = None, priority: int = 50, payload: dict | None = None) -> tuple[GenesisTask, bool]:
        """Create a deterministic task once, returning (task, created)."""
        dedupe_key = dedupe_key.strip()
        if not dedupe_key:
            raise ValueError("dedupe_key is required")
        objective = objective.strip()
        if not objective:
            raise ValueError("objective is required")
        if priority < 0 or priority > 100:
            raise ValueError("priority must be between 0 and 100")
        task_id = "task-" + hashlib.sha256(dedupe_key.encode("utf-8")).hexdigest()[:16]
        existing = self.get(task_id)
        if existing is not None:
            return existing, False
        now = utc_now()
        task_payload = dict(payload or {})
        task_payload.setdefault("dedupe_key", dedupe_key)
        task = GenesisTask(task_id, objective, module_id, "new", priority, task_payload, now, now)
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
        with self._connect() as db:
            db.execute(
                "UPDATE genesis_tasks SET state = ?, module_id = ?, updated_at = ? WHERE task_id = ?",
                (new_state, assigned_module, now, task_id),
            )
        updated = self.get(task_id)
        assert updated is not None
        return updated

    @staticmethod
    def _from_row(row: sqlite3.Row) -> GenesisTask:
        return GenesisTask(
            task_id=row["task_id"],
            objective=row["objective"],
            module_id=row["module_id"],
            state=row["state"],
            priority=row["priority"],
            payload=json.loads(row["payload_json"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
