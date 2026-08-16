from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from typing import Any


class KnowledgeStore:
    """Provenance-aware knowledge storage.

    New knowledge is always stored as candidate unless an external validation
    process explicitly promotes it. This prevents user/model output from being
    treated as truth automatically.
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS knowledge (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                claim TEXT NOT NULL,
                source TEXT NOT NULL,
                source_type TEXT NOT NULL,
                evidence_level TEXT NOT NULL,
                status TEXT NOT NULL,
                content_hash TEXT NOT NULL UNIQUE,
                metadata TEXT NOT NULL
            )
            """
        )
        self.conn.commit()

    def add_candidate(
        self,
        claim: str,
        source: str,
        source_type: str = "unknown",
        evidence_level: str = "unreviewed",
        metadata: dict[str, Any] | None = None,
    ) -> str:
        normalized = claim.strip()
        digest = hashlib.sha256(
            json.dumps(
                {"claim": normalized, "source": source},
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        now = datetime.now(timezone.utc).isoformat()
        self.conn.execute(
            """
            INSERT OR IGNORE INTO knowledge(
                created_at, claim, source, source_type, evidence_level,
                status, content_hash, metadata
            ) VALUES(?,?,?,?,?,?,?,?)
            """,
            (
                now,
                normalized,
                source,
                source_type,
                evidence_level,
                "candidate",
                digest,
                json.dumps(metadata or {}, sort_keys=True),
            ),
        )
        self.conn.commit()
        return digest

    def promote(self, content_hash: str, validation_note: str) -> bool:
        cur = self.conn.execute(
            "UPDATE knowledge SET status='validated', metadata=? WHERE content_hash=? AND status='candidate'",
            (json.dumps({"validation_note": validation_note}, sort_keys=True), content_hash),
        )
        self.conn.commit()
        return cur.rowcount == 1

    def counts(self) -> dict[str, int]:
        rows = self.conn.execute(
            "SELECT status, COUNT(*) FROM knowledge GROUP BY status"
        ).fetchall()
        return {status: count for status, count in rows}
