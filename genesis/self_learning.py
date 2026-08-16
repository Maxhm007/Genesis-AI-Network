from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


LESSON_STATES = {"candidate", "validated", "rejected"}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class LearningLesson:
    lesson_id: str
    source_type: str
    source_ref: str
    topic: str
    lesson: str
    evidence: dict[str, Any]
    confidence: float
    state: str
    created_at: str
    updated_at: str


class SelfLearningStore:
    """Persistent, provenance-aware lessons for Genesis.

    Lessons enter as candidates. Generated analysis, benchmark observations,
    failures, or peer feedback do not become validated knowledge merely because
    Genesis produced them. Validation is an explicit separate transition.
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
                CREATE TABLE IF NOT EXISTS learning_lessons (
                    lesson_id TEXT PRIMARY KEY,
                    source_type TEXT NOT NULL,
                    source_ref TEXT NOT NULL,
                    topic TEXT NOT NULL,
                    lesson TEXT NOT NULL,
                    evidence_json TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    state TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            db.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS learning_source_ref_uq ON learning_lessons(source_type, source_ref)"
            )

    @staticmethod
    def _id(source_type: str, source_ref: str) -> str:
        digest = hashlib.sha256(f"{source_type}\0{source_ref}".encode("utf-8")).hexdigest()[:20]
        return "lesson-" + digest

    def add_candidate(
        self,
        *,
        source_type: str,
        source_ref: str,
        topic: str,
        lesson: str,
        evidence: dict[str, Any] | None = None,
        confidence: float = 0.5,
    ) -> LearningLesson:
        source_type = source_type.strip()
        source_ref = source_ref.strip()
        topic = topic.strip()
        lesson = lesson.strip()
        if not all((source_type, source_ref, topic, lesson)):
            raise ValueError("source_type, source_ref, topic, and lesson are required")
        confidence = max(0.0, min(float(confidence), 1.0))
        existing = self.by_source(source_type, source_ref)
        if existing:
            return existing
        now = utc_now()
        item = LearningLesson(
            lesson_id=self._id(source_type, source_ref),
            source_type=source_type,
            source_ref=source_ref,
            topic=topic,
            lesson=lesson,
            evidence=dict(evidence or {}),
            confidence=confidence,
            state="candidate",
            created_at=now,
            updated_at=now,
        )
        with self._connect() as db:
            db.execute(
                "INSERT INTO learning_lessons VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    item.lesson_id,
                    item.source_type,
                    item.source_ref,
                    item.topic,
                    item.lesson,
                    json.dumps(item.evidence, sort_keys=True),
                    item.confidence,
                    item.state,
                    item.created_at,
                    item.updated_at,
                ),
            )
        return item

    def by_source(self, source_type: str, source_ref: str) -> LearningLesson | None:
        with self._connect() as db:
            row = db.execute(
                "SELECT * FROM learning_lessons WHERE source_type = ? AND source_ref = ?",
                (source_type, source_ref),
            ).fetchone()
        return self._from_row(row) if row else None

    def get(self, lesson_id: str) -> LearningLesson | None:
        with self._connect() as db:
            row = db.execute("SELECT * FROM learning_lessons WHERE lesson_id = ?", (lesson_id,)).fetchone()
        return self._from_row(row) if row else None

    def list(self, state: str | None = None, limit: int = 100) -> list[LearningLesson]:
        if state is not None and state not in LESSON_STATES:
            raise ValueError("invalid lesson state")
        query = "SELECT * FROM learning_lessons"
        params: list[object] = []
        if state:
            query += " WHERE state = ?"
            params.append(state)
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        with self._connect() as db:
            rows = db.execute(query, params).fetchall()
        return [self._from_row(row) for row in rows]

    def transition(self, lesson_id: str, new_state: str, *, validation_evidence: dict[str, Any] | None = None) -> LearningLesson:
        if new_state not in {"validated", "rejected"}:
            raise ValueError("lessons may only transition to validated or rejected")
        current = self.get(lesson_id)
        if current is None:
            raise KeyError(lesson_id)
        if current.state != "candidate":
            raise ValueError("only candidate lessons may be validated or rejected")
        if new_state == "validated" and not validation_evidence:
            raise ValueError("validation evidence is required")
        evidence = dict(current.evidence)
        if validation_evidence:
            evidence["validation"] = validation_evidence
        now = utc_now()
        with self._connect() as db:
            db.execute(
                "UPDATE learning_lessons SET state = ?, evidence_json = ?, updated_at = ? WHERE lesson_id = ?",
                (new_state, json.dumps(evidence, sort_keys=True), now, lesson_id),
            )
        updated = self.get(lesson_id)
        assert updated is not None
        return updated

    @staticmethod
    def _from_row(row: sqlite3.Row) -> LearningLesson:
        return LearningLesson(
            lesson_id=row["lesson_id"],
            source_type=row["source_type"],
            source_ref=row["source_ref"],
            topic=row["topic"],
            lesson=row["lesson"],
            evidence=json.loads(row["evidence_json"]),
            confidence=float(row["confidence"]),
            state=row["state"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )


class SelfLearningEngine:
    """Convert bounded runtime experience into candidate lessons."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root).resolve()
        self.store = SelfLearningStore(self.root / "runtime" / "self_learning.sqlite3")

    def learn_from_research_reviews(self) -> list[LearningLesson]:
        review_dir = self.root / "runtime" / "research_reviews"
        if not review_dir.exists():
            return []
        learned: list[LearningLesson] = []
        for path in sorted(review_dir.glob("*.json")):
            payload = json.loads(path.read_text(encoding="utf-8"))
            task = payload.get("task", {})
            outputs = payload.get("team_outputs", [])
            completed = [item for item in outputs if item.get("status") == "completed" and item.get("output")]
            if not completed:
                continue
            lesson_text = "\n\n".join(
                f"{item.get('agent')}: {str(item.get('output'))[:2500]}" for item in completed[:4]
            )
            learned.append(
                self.store.add_candidate(
                    source_type="research_review",
                    source_ref=str(task.get("task_id") or path.stem),
                    topic=str(task.get("objective") or "immortality research review")[:500],
                    lesson=lesson_text,
                    evidence={
                        "review_file": str(path.relative_to(self.root)),
                        "source_url": task.get("payload", {}).get("url"),
                        "rule": payload.get("rule"),
                        "team_members": [item.get("agent") for item in completed],
                    },
                    confidence=0.45,
                )
            )
        return learned

    def learn_from_ai_score(self) -> LearningLesson | None:
        path = self.root / "runtime" / "ai_score.json"
        if not path.exists():
            return None
        payload = json.loads(path.read_text(encoding="utf-8"))
        gaps = payload.get("priority_gaps", [])
        if not gaps:
            return None
        gap = gaps[0]
        ref = f"{payload.get('created_at','unknown')}:{gap.get('name','unknown')}"
        lesson = (
            f"The current competitive AI score is {payload.get('score')}/{payload.get('max_score')}. "
            f"The weakest measured dimension is {gap.get('name')} at {gap.get('score')}/{gap.get('max_score')}. "
            f"Next evidence-seeking action: {gap.get('improvement_hint') or 'measure and improve this dimension.'}"
        )
        return self.store.add_candidate(
            source_type="competitive_score",
            source_ref=ref,
            topic="competitive capability gap",
            lesson=lesson,
            evidence={"score_report": "runtime/ai_score.json", "gap": gap},
            confidence=0.9,
        )

    def run_once(self) -> dict[str, Any]:
        research = self.learn_from_research_reviews()
        score_lesson = self.learn_from_ai_score()
        candidates = self.store.list(state="candidate", limit=100)
        summary = {
            "created_at": utc_now(),
            "research_lessons_seen": len(research),
            "score_lesson_seen": score_lesson is not None,
            "candidate_lessons": len(candidates),
            "validated_lessons": len(self.store.list(state="validated", limit=1000)),
            "rule": "Self-learning creates provenance-linked candidate lessons only. Validation remains separate.",
        }
        out = self.root / "runtime" / "self_learning_status.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
        return summary
