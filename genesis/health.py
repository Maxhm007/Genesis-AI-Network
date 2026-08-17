from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone

@dataclass(frozen=True)
class HealthSnapshot:
    status: str
    created_at: str
    details: dict

def build_health_snapshot(**details) -> dict:
    status = details.pop('status', 'ok')
    snap = HealthSnapshot(status=status, created_at=datetime.now(timezone.utc).isoformat(), details=details)
    return asdict(snap)
