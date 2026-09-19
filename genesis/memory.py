from __future__ import annotations

import hashlib
import hmac
import json
import math
import re
import sqlite3
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


MEMORY_TYPES = {"semantic", "episodic", "procedural", "policy_context", "decision", "repair"}
MEMORY_STATES = {"candidate", "validated", "rejected", "expired", "superseded"}
MAX_MEMORY_ITEMS = 5000
MAX_TOPIC_CHARS = 500
MAX_CONTENT_CHARS = 8000
MAX_SOURCE_TYPE_CHARS = 100
MAX_SOURCE_REF_CHARS = 500
MAX_METADATA_CHARS = 16000

_SECRET_PATTERNS = (
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----", re.IGNORECASE),
    re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b"),
    re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"(?i)\b(?:password|passwd|secret|api[_-]?key|access[_-]?token|authorization)\s*[:=]\s*[^\s,;]{8,}"),
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _tokens(text: str) -> set[str]:
    return {token for token in re.findall(r"[a-z0-9_]{2,}", text.lower())}


def is_genesis_root(root: Path) -> bool:
    path = Path(root).resolve()
    return (
        (path / "genesis").is_dir()
        and (path / "GENESIS_BLOCK.json").is_file()
        and (path / "GENESIS_CONSTITUTION.md").is_file()
    )


def contains_sensitive_material(value: object) -> bool:
    try:
        text = value if isinstance(value, str) else json.dumps(value, sort_keys=True, default=str)
    except (TypeError, ValueError):
        text = str(value)
    return any(pattern.search(text) for pattern in _SECRET_PATTERNS)


def _bounded_text(value: object, limit: int, field: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{field} is required")
    if len(text) > limit:
        raise ValueError(f"{field} exceeds memory bound")
    if contains_sensitive_material(text):
        raise ValueError(f"{field} contains sensitive material")
    return text


def _portable_payload(item: "MemoryItem") -> dict[str, Any]:
    payload = asdict(item)
    payload["metadata"] = dict(item.metadata)
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return {
        "schema": "genesis-memory-v1",
        "record": payload,
        "integrity_sha256": hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
    }


def _verify_portable_payload(payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("schema") != "genesis-memory-v1" or not isinstance(payload.get("record"), dict):
        raise ValueError("invalid portable memory schema")
    record = dict(payload["record"])
    expected = str(payload.get("integrity_sha256") or "")
    canonical = json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    actual = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    if not expected or not hmac.compare_digest(expected, actual):
        raise ValueError("portable memory integrity check failed")
    if record.get("state") != "validated":
        raise ValueError("only validated memory may be imported as trusted portable memory")
    metadata = record.get("metadata")
    if not isinstance(metadata, dict) or not metadata.get("validation"):
        raise ValueError("portable validated memory requires validation evidence")
    if contains_sensitive_material(record):
        raise ValueError("portable memory contains sensitive material")
    return record


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
        topic = _bounded_text(topic, MAX_TOPIC_CHARS, "topic")
        content = _bounded_text(content, MAX_CONTENT_CHARS, "content")
        source_type = _bounded_text(source_type, MAX_SOURCE_TYPE_CHARS, "source_type")
        source_ref = _bounded_text(source_ref, MAX_SOURCE_REF_CHARS, "source_ref")
        metadata = dict(metadata or {})
        if contains_sensitive_material(metadata):
            raise ValueError("metadata contains sensitive material")
        metadata_json = json.dumps(metadata, sort_keys=True)
        if len(metadata_json) > MAX_METADATA_CHARS:
            raise ValueError("metadata exceeds memory bound")
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
            metadata=metadata,
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
                    item.importance, item.state, metadata_json,
                    item.created_at, item.updated_at, item.last_accessed_at,
                    item.access_count,
                ),
            )
        stored = self.get(item.memory_id) or item
        self.prune()
        return stored

    def get(self, memory_id: str) -> MemoryItem | None:
        with self._connect() as db:
            row = db.execute("SELECT * FROM genesis_memory WHERE memory_id = ?", (memory_id,)).fetchone()
        return self._from_row(row) if row else None

    def transition(self, memory_id: str, new_state: str, *, evidence: dict[str, Any] | None = None) -> MemoryItem:
        if new_state not in {"validated", "rejected", "expired", "superseded"}:
            raise ValueError("invalid memory transition")
        current = self.get(memory_id)
        if current is None:
            raise KeyError(memory_id)
        if current.state != "candidate" and new_state in {"validated", "rejected"}:
            raise ValueError("only candidate memories may be validated or rejected")
        if new_state == "superseded" and current.state != "validated":
            raise ValueError("only validated memories may be superseded")
        if new_state == "validated" and not evidence:
            raise ValueError("validation evidence is required")
        metadata = dict(current.metadata)
        if evidence:
            if contains_sensitive_material(evidence):
                raise ValueError("memory transition evidence contains sensitive material")
            metadata["validation" if new_state == "validated" else "lifecycle_evidence"] = evidence
        now = utc_now()
        with self._connect() as db:
            db.execute(
                "UPDATE genesis_memory SET state = ?, metadata_json = ?, updated_at = ? WHERE memory_id = ?",
                (new_state, json.dumps(metadata, sort_keys=True), now, memory_id),
            )
        updated = self.get(memory_id)
        assert updated is not None
        return updated


    def portable_payload(self, memory_id: str) -> dict[str, Any]:
        item = self.get(memory_id)
        if item is None:
            raise KeyError(memory_id)
        if item.state != "validated":
            raise ValueError("only validated memory may be exported")
        return _portable_payload(item)

    def import_portable(self, payload: dict[str, Any]) -> MemoryItem:
        record = _verify_portable_payload(payload)
        item = self.add(
            memory_type=str(record["memory_type"]),
            topic=str(record["topic"]),
            content=str(record["content"]),
            source_type=str(record["source_type"]),
            source_ref=str(record["source_ref"]),
            confidence=float(record["confidence"]),
            importance=float(record["importance"]),
            state="candidate",
            metadata=dict(record.get("metadata") or {}),
        )
        current = self.get(item.memory_id)
        assert current is not None
        if current.state == "candidate":
            validation = dict(record["metadata"]["validation"])
            current = self.transition(current.memory_id, "validated", evidence=validation)
        return current

    def supersede_knowledge_key(
        self,
        knowledge_key: str,
        *,
        keep_memory_id: str,
        evidence: dict[str, Any],
    ) -> int:
        key = str(knowledge_key or "").strip()
        if not key:
            return 0
        changed = 0
        with self._connect() as db:
            rows = db.execute(
                "SELECT * FROM genesis_memory WHERE state = 'validated' AND memory_id != ?",
                (keep_memory_id,),
            ).fetchall()
        for row in rows:
            item = self._from_row(row)
            if str(item.metadata.get("knowledge_key") or "") != key:
                continue
            self.transition(item.memory_id, "superseded", evidence=evidence)
            changed += 1
        return changed

    def prune(self, *, max_items: int = MAX_MEMORY_ITEMS) -> int:
        bound = int(max_items)
        if bound < 100 or bound > 100_000:
            raise ValueError("memory retention bound is out of range")
        with self._connect() as db:
            total = int(db.execute("SELECT COUNT(*) FROM genesis_memory").fetchone()[0])
            excess = total - bound
            if excess <= 0:
                return 0
            rows = db.execute(
                """
                SELECT memory_id FROM genesis_memory
                ORDER BY
                    CASE state
                        WHEN 'rejected' THEN 0
                        WHEN 'expired' THEN 1
                        WHEN 'superseded' THEN 2
                        WHEN 'candidate' THEN 3
                        ELSE 4
                    END ASC,
                    importance ASC,
                    updated_at ASC
                LIMIT ?
                """,
                (excess,),
            ).fetchall()
            ids = [str(row["memory_id"]) for row in rows]
            db.executemany("DELETE FROM genesis_memory WHERE memory_id = ?", [(mid,) for mid in ids])
        return len(ids)

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
            metadata={"lesson_evidence": dict(lesson.evidence)}
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


    def remember_verified_repair(
        self,
        *,
        issue_number: int,
        issue_title: str,
        target: str,
        problem_class: str,
        root_cause: str,
        promoted_sha: str,
        candidate_sha: str,
        worker_run: str,
        provider: str,
        failed_approaches: list[dict[str, Any]] | None = None,
    ) -> MemoryItem:
        target = _bounded_text(target, 500, "target")
        problem_class = _bounded_text(problem_class or "github_reported_issue", 200, "problem_class")
        root_cause = _bounded_text(root_cause or "verified repository defect", 1200, "root_cause")
        issue_title = _bounded_text(issue_title, 500, "issue_title")
        promoted_sha = _bounded_text(promoted_sha, 100, "promoted_sha")
        candidate_sha = _bounded_text(candidate_sha, 100, "candidate_sha")
        worker_run = _bounded_text(worker_run, 100, "worker_run")
        provider = _bounded_text(provider or "unknown", 200, "provider")
        failed = []
        for row in (failed_approaches or [])[-6:]:
            if not isinstance(row, dict):
                continue
            failed.append({
                "provider": str(row.get("provider") or "unknown")[:200],
                "outcome": str(row.get("outcome") or "unknown")[:200],
                "validation": str(row.get("validation") or "")[:500],
            })
        if contains_sensitive_material(failed):
            failed = [{"outcome": "redacted_sensitive_validation"}]

        knowledge_key = f"repair:{target}:{problem_class}".lower()
        content = (
            f"Verified repair for issue #{int(issue_number)} ({issue_title}). "
            f"Problem class: {problem_class}. Root cause/evidence summary: {root_cause}. "
            f"Successful fix changed {target}; candidate {candidate_sha} was promoted as {promoted_sha} "
            "after target and full repository validation."
        )
        candidate = self.store.add(
            memory_type="repair",
            topic=f"{problem_class} {target}",
            content=content,
            source_type="verified_github_repair",
            source_ref=f"issue:{int(issue_number)}:commit:{promoted_sha}",
            confidence=1.0,
            importance=0.95,
            state="candidate",
            metadata={
                "knowledge_key": knowledge_key,
                "issue_number": int(issue_number),
                "target": target,
                "provider": provider,
                "worker_run": worker_run,
                "candidate_sha": candidate_sha,
                "promoted_sha": promoted_sha,
                "failed_approaches": failed,
            },
        )
        if candidate.state == "candidate":
            candidate = self.store.transition(
                candidate.memory_id,
                "validated",
                evidence={
                    "issue_number": int(issue_number),
                    "promoted_sha": promoted_sha,
                    "worker_run": worker_run,
                    "target_and_full_suite_passed": True,
                },
            )
        self.store.supersede_knowledge_key(
            knowledge_key,
            keep_memory_id=candidate.memory_id,
            evidence={
                "reason": "newer verified repair for same target/problem class",
                "replacement_memory_id": candidate.memory_id,
                "promoted_sha": promoted_sha,
            },
        )
        return candidate

    def recall(self, query: str, *, limit: int = 6) -> list[dict[str, Any]]:
        return self.store.context(query, limit=limit)

    def write_status(self, path: Path) -> dict[str, Any]:
        payload = {"created_at": utc_now(), **self.store.stats()}
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return payload
