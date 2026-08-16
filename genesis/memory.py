from __future__ import annotations

import hashlib
import json
import math
import re
import sqlite3
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


MEMORY_TYPES = {"semantic", "episodic", "procedural", "policy_context"}
MEMORY_STATES = {"candidate", "validated", "rejected", "expired"}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _tokens(text: str) -> set[str]:
    return {token for token in re.findall(r"[a-z0-9_]{2,}", text.lower())}


@dataclass(frozen=True)
class MemoryItem:
    memory_id: str
    memory_type: str
    topic: str
    content: str
    source_type: str
    source_ref: str
    confidence: float
    importance: float
    state: str
    metadata: dict[str, Any]
    created_at: str
    updated_at: str
    last_accessed_at: str | None
    access_count: int


class MemoryStore:
    """Persistent bounded memory for Genesis.

    Memory is not truth. New memories are candidates unless explicitly created
    from already validated evidence or promoted by a separate validation step.
    Normal retrieval returns validated memories only.
    """

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.path)
        db.row_factory = sqlite3.Row
        return db

    def _init_db(self) -> None:
        with self._connect() as db:
            db.execute(
                """
                CREATE TABLE IF NOT EXISTS genesis_memory (
                    memory_id TEXT PRIMARY KEY,
                    memory_type TEXT NOT NULL,
                    topic TEXT NOT NULL,
                    content TEXT NOT NULL,
                    source_type TEXT NOT NULL,
                    source_ref TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    importance REAL NOT NULL,
                    state TEXT NOT NULL,
                    metadata_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    last_accessed_at TEXT,
                    access_count INTEGER NOT NULL DEFAULT 0,
                    UNIQUE(source_type, source_ref, content)
                )
                """
            )
            db.execute("CREATE INDEX IF NOT EXISTS genesis_memory_state_idx ON genesis_memory(state)")
            db.execute("CREATE INDEX IF NOT EXISTS genesis_memory_type_idx ON genesis_memory(memory_type)")

    @staticmethod
    def _id(source_type: str, source_ref: str, content: str) -> str:
        digest = hashlib.sha256(f"{source_type}\0{source_ref}\0{content}".encode("utf-8")).hexdigest()[:20]
        return "memory-" + digest

    def add(
        self,
        *,
        memory_type: str,
        topic: str,
        content: str,
        source_type: str,
        source_ref: str,
        confidence: float = 0.5,
        importance: float = 0.5,
        state: str = "candidate",
        metadata: dict[str, Any] | None = None,
    ) -> MemoryItem:
        if memory_type not in MEMORY_TYPES:
            raise ValueError("invalid memory type")
        if state not in MEMORY_STATES:
            raise ValueError("invalid memory state")
        topic = topic.strip()
        content = content.strip()
        source_type = source_type.strip()
        source_ref = source_ref.strip()
        if not all((topic, content, source_type, source_ref)):
            raise ValueError("topic, content, source_type and source_ref are required")
        confidence = max(0.0, min(float(confidence), 1.0))
        importance = max(0.0, min(float(importance), 1.0))
        now = utc_now()
        item = MemoryItem(
            memory_id=self._id(source_type, source_ref, content),
            memory_type=memory_type,
            topic=topic,
            content=content,
            source_type=source_type,
            source_ref=source_ref,
            confidence=confidence,
            importance=importance,
            state=state,
            metadata=dict(metadata or {}),
            created_at=now,
            updated_at=now,
            last_accessed_at=None,
            access_count=0,
        )
        with self._connect() as db:
            db.execute(
                """
                INSERT OR IGNORE INTO genesis_memory VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    item.memory_id, item.memory_type, item.topic, item.content,
                    item.source_type, item.source_ref, item.confidence,
                    item.importance, item.state, json.dumps(item.metadata, sort_keys=True),
                    item.created_at, item.updated_at, item.last_accessed_at,
                    item.access_count,
                ),
            )
        return self.get(item.memory_id) or item

    def get(self, memory_id: str) -> MemoryItem | None:
        with self._connect() as db:
            row = db.execute("SELECT * FROM genesis_memory WHERE memory_id = ?", (memory_id,)).fetchone()
        return self._from_row(row) if row else None

    def transition(self, memory_id: str, new_state: str, *, evidence: dict[str, Any] | None = None) -> MemoryItem:
        if new_state not in {"validated", "rejected", "expired"}:
            raise ValueError("invalid memory transition")
        current = self.get(memory_id)
        if current is None:
            raise KeyError(memory_id)
        if current.state != "candidate" and new_state in {"validated", "rejected"}:
            raise ValueError("only candidate memories may be validated or rejected")
        if new_state == "validated" and not evidence:
            raise ValueError("validation evidence is required")
        metadata = dict(current.metadata)
        if evidence:
            metadata["validation"] = evidence
        now = utc_now()
        with self._connect() as db:
            db.execute(
                "UPDATE genesis_memory SET state = ?, metadata_json = ?, updated_at = ? WHERE memory_id = ?",
                (new_state, json.dumps(metadata, sort_keys=True), now, memory_id),
            )
        updated = self.get(memory_id)
        assert updated is not None
        return updated

    def retrieve(
        self,
        query: str,
        *,
        limit: int = 6,
        memory_types: set[str] | None = None,
        include_candidates: bool = False,
    ) -> list[MemoryItem]:
        query_tokens = _tokens(query)
        states = ["validated"] + (["candidate"] if include_candidates else [])
        placeholders = ",".join("?" for _ in states)
        with self._connect() as db:
            rows = db.execute(
                f"SELECT * FROM genesis_memory WHERE state IN ({placeholders}) ORDER BY created_at DESC LIMIT 1000",
                states,
            ).fetchall()
        now = datetime.now(timezone.utc)
        ranked: list[tuple[float, MemoryItem]] = []
        for row in rows:
            item = self._from_row(row)
            if memory_types and item.memory_type not in memory_types:
                continue
            item_tokens = _tokens(item.topic + " " + item.content)
            overlap = len(query_tokens & item_tokens) / max(1, len(query_tokens | item_tokens)) if query_tokens else 0.0
            created = datetime.fromisoformat(item.created_at.replace("Z", "+00:00"))
            age_days = max(0.0, (now - created.astimezone(timezone.utc)).total_seconds() / 86400.0)
            recency = math.exp(-age_days / 365.0)
            score = (0.55 * overlap) + (0.20 * item.confidence) + (0.15 * item.importance) + (0.10 * recency)
            if query_tokens and overlap == 0:
                continue
            ranked.append((score, item))
        ranked.sort(key=lambda pair: pair[0], reverse=True)
        selected = [item for _, item in ranked[: max(1, min(limit, 20))]]
        if selected:
            stamp = utc_now()
            with self._connect() as db:
                db.executemany(
                    "UPDATE genesis_memory SET last_accessed_at = ?, access_count = access_count + 1 WHERE memory_id = ?",
                    [(stamp, item.memory_id) for item in selected],
                )
        return selected

    def context(self, query: str, *, limit: int = 6) -> list[dict[str, Any]]:
        return [
            {
                "memory_id": item.memory_id,
                "type": item.memory_type,
                "topic": item.topic,
                "content": item.content,
                "confidence": item.confidence,
                "source_type": item.source_type,
                "source_ref": item.source_ref,
            }
            for item in self.retrieve(query, limit=limit)
        ]

    def stats(self) -> dict[str, Any]:
        with self._connect() as db:
            rows = db.execute("SELECT state, memory_type, COUNT(*) AS n FROM genesis_memory GROUP BY state, memory_type").fetchall()
        return {
            "total": sum(int(row["n"]) for row in rows),
            "by_state_type": [dict(row) for row in rows],
        }

    @staticmethod
    def _from_row(row: sqlite3.Row) -> MemoryItem:
        return MemoryItem(
            memory_id=row["memory_id"],
            memory_type=row["memory_type"],
            topic=row["topic"],
            content=row["content"],
            source_type=row["source_type"],
            source_ref=row["source_ref"],
            confidence=float(row["confidence"]),
            importance=float(row["importance"]),
            state=row["state"],
            metadata=json.loads(row["metadata_json"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            last_accessed_at=row["last_accessed_at"],
            access_count=int(row["access_count"]),
        )


class GenesisMemory:
    """High-level bridge between validated learning and runtime recall."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root).resolve()
        self.store = MemoryStore(self.root / "runtime" / "memory.sqlite3")

    def remember_validated_lesson(self, lesson: Any) -> MemoryItem:
        if getattr(lesson, "state", None) != "validated":
            raise ValueError("only validated lessons may enter trusted memory")
        return self.store.add(
            memory_type="procedural",
            topic=str(lesson.topic),
            content=str(lesson.lesson),
            source_type="validated_lesson",
            source_ref=str(lesson.lesson_id),
            confidence=float(lesson.confidence),
            importance=0.8,
            state="validated",
            metadata={"lesson_evidence": dict(lesson.evidence)},
        )

    def remember_event(self, *, topic: str, content: str, source_ref: str, success: bool) -> MemoryItem:
        return self.store.add(
            memory_type="episodic",
            topic=topic,
            content=content,
            source_type="runtime_event",
            source_ref=source_ref,
            confidence=1.0,
            importance=0.7 if success else 0.85,
            state="validated",
            metadata={"observed_runtime_event": True, "success": bool(success)},
        )

    def recall(self, query: str, *, limit: int = 6) -> list[dict[str, Any]]:
        return self.store.context(query, limit=limit)

    def write_status(self, path: Path) -> dict[str, Any]:
        payload = {"created_at": utc_now(), **self.store.stats()}
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return payload
