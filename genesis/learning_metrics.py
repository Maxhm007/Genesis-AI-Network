"""Evidence-based measurements of Genesis's research-to-upgrade learning funnel.

This module only reads existing durable evidence. It does not claim that code
promotion improves model quality or independently relax promotion gates.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path


def learning_metrics(db_path: Path) -> dict:
    db_path = Path(db_path)
    if not db_path.is_file():
        return {"status": "no_evidence", "research_total": 0, "opportunity_total": 0,
                "promoted_total": 0, "promotion_rate": None, "research_states": {},
                "opportunity_states": {}, "recent_failure_reasons": []}

    with sqlite3.connect(f"file:{db_path.resolve()}?mode=ro", uri=True) as db:
        db.row_factory = sqlite3.Row
        research = {str(row["status"]): int(row["n"]) for row in db.execute(
            "SELECT status, COUNT(*) AS n FROM research_items GROUP BY status"
        )}
        opportunities = {str(row["state"]): int(row["n"]) for row in db.execute(
            "SELECT state, COUNT(*) AS n FROM upgrade_opportunities GROUP BY state"
        )}
        failures = []
        for row in db.execute(
            "SELECT message, details_json FROM upgrade_events "
            "WHERE status IN ('failed','quarantined','rejected','error') "
            "ORDER BY event_id DESC LIMIT 10"
        ):
            details = {}
            try:
                parsed = json.loads(row["details_json"] or "{}")
                if isinstance(parsed, dict):
                    details = parsed
            except (ValueError, TypeError):
                pass
            failures.append({"message": str(row["message"])[:300],
                             "reason": str(details.get("reason") or details.get("error") or "")[:300]})
    total = sum(opportunities.values())
    promoted = opportunities.get("promoted", 0) + opportunities.get("closed", 0)
    return {
        "status": "evidence_available", "research_total": sum(research.values()),
        "opportunity_total": total, "promoted_total": promoted,
        "promotion_rate": round(promoted / total, 4) if total else None,
        "research_states": research, "opportunity_states": opportunities,
        "recent_failure_reasons": failures,
        "measurement_note": "Promotion-rate counts lifecycle states, not measured performance gains.",
    }
