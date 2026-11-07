"""Durable bounded repair attempts. No test output or secrets are persisted."""
from __future__ import annotations

import hashlib
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

MAX_IDENTICAL_ATTEMPTS = 3


def fingerprint(category: str, failure_text: str) -> str:
    """Stable signature, excluding volatile pytest durations and paths where possible."""
    import re
    lines = []
    for line in failure_text.splitlines():
        line = line.strip()
        if line.startswith(("FAILED ", "ERROR ", "E   ", "ModuleNotFoundError:", "ImportError:", "SyntaxError:")):
            line = re.sub(r"\b\d+\.\d+s\b", "<duration>", line)
            lines.append(line[:500])
    signature = "\n".join(sorted(set(lines))) or failure_text[-2000:]
    return hashlib.sha256((category + "\n" + signature).encode("utf-8")).hexdigest()


class RepairCheckpointStore:
    """Local SQLite ledger; attempts are reserved before generating a repair."""

    def __init__(self, root: Path):
        path = Path(root).resolve() / "runtime" / "repair_checkpoints.sqlite3"
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        with self._connect() as db:
            db.execute("""
                CREATE TABLE IF NOT EXISTS repair_attempts (
                    signature TEXT PRIMARY KEY,
                    category TEXT NOT NULL,
                    attempts INTEGER NOT NULL DEFAULT 0,
                    state TEXT NOT NULL,
                    last_result TEXT NOT NULL DEFAULT '',
                    updated_at TEXT NOT NULL
                )
            """)

    def _connect(self):
        db = sqlite3.connect(self.path, timeout=30)
        db.execute("PRAGMA busy_timeout=30000")
        return db

    def reserve(self, signature: str, category: str, *, limit: int = MAX_IDENTICAL_ATTEMPTS) -> bool:
        if not 1 <= limit <= 10:
            raise ValueError("invalid repair attempt limit")
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT attempts, state FROM repair_attempts WHERE signature=?", (signature,)).fetchone()
            if row is not None and (row[0] >= limit or row[1] == "verified"):
                return False
            attempts = row[0] + 1 if row else 1
            db.execute("""
                INSERT INTO repair_attempts(signature, category, attempts, state, updated_at)
                VALUES (?, ?, ?, 'in_progress', ?)
                ON CONFLICT(signature) DO UPDATE SET
                  attempts=excluded.attempts, state='in_progress', updated_at=excluded.updated_at
            """, (signature, category, attempts, datetime.now(timezone.utc).isoformat()))
            return True

    def finish(self, signature: str, state: str, result: str = "") -> None:
        if state not in {"candidate_created", "failed", "blocked", "verified"}:
            raise ValueError("invalid checkpoint state")
        with self._connect() as db:
            cursor = db.execute("""
                UPDATE repair_attempts SET state=?, last_result=?, updated_at=?
                WHERE signature=?
            """, (state, result[:200], datetime.now(timezone.utc).isoformat(), signature))
            if cursor.rowcount != 1:
                raise KeyError(signature)

    def get(self, signature: str) -> dict | None:
        with self._connect() as db:
            row = db.execute(
                "SELECT category, attempts, state, last_result FROM repair_attempts WHERE signature=?",
                (signature,),
            ).fetchone()
        return dict(zip(("category", "attempts", "state", "last_result"), row)) if row else None
