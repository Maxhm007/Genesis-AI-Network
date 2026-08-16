from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


class EvolutionManager:
    """Creates isolated improvement proposals; never self-promotes them."""

    def __init__(self, root: Path, conn: sqlite3.Connection) -> None:
        self.root = root
        self.conn = conn
        self.candidate_dir = root / "candidates"
        self.candidate_dir.mkdir(parents=True, exist_ok=True)
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS evolution_candidates (
                id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                title TEXT NOT NULL,
                rationale TEXT NOT NULL,
                status TEXT NOT NULL,
                proposal_path TEXT NOT NULL,
                validation TEXT NOT NULL
            )
            """
        )
        self.conn.commit()

    def propose(self, title: str, rationale: str, changes: dict) -> str:
        created_at = datetime.now(timezone.utc).isoformat()
        payload = {
            "title": title,
            "rationale": rationale,
            "changes": changes,
            "created_at": created_at,
            "status": "candidate",
        }
        candidate_id = hashlib.sha256(
            json.dumps(payload, sort_keys=True).encode("utf-8")
        ).hexdigest()[:16]
        proposal_path = self.candidate_dir / f"{candidate_id}.json"
        proposal_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        self.conn.execute(
            "INSERT OR IGNORE INTO evolution_candidates VALUES(?,?,?,?,?,?,?)",
            (candidate_id, created_at, title, rationale, "candidate", str(proposal_path), "{}"),
        )
        self.conn.commit()
        return candidate_id

    def validate_structure(self, candidate_id: str) -> bool:
        row = self.conn.execute(
            "SELECT proposal_path,status FROM evolution_candidates WHERE id=?",
            (candidate_id,),
        ).fetchone()
        if not row or row[1] != "candidate":
            return False
        path = Path(row[0])
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            ok = (
                payload.get("status") == "candidate"
                and isinstance(payload.get("changes"), dict)
                and bool(payload.get("rationale"))
            )
        except Exception as exc:
            ok = False
            details = {"structural_validation": False, "error": str(exc)}
        else:
            details = {"structural_validation": ok}
        self.conn.execute(
            "UPDATE evolution_candidates SET validation=? WHERE id=?",
            (json.dumps(details, sort_keys=True), candidate_id),
        )
        self.conn.commit()
        return ok

    def status_counts(self) -> dict[str, int]:
        rows = self.conn.execute(
            "SELECT status, COUNT(*) FROM evolution_candidates GROUP BY status"
        ).fetchall()
        return {status: count for status, count in rows}
