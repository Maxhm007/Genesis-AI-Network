from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path


@dataclass(frozen=True)
class EfficiencyRecord:
    task_type: str
    provider: str
    success: bool
    quality: float
    latency_seconds: float
    compute_units: float
    monetary_cost_usd: float
    created_at: str


class EfficiencyTracker:
    """Measure capability-per-resource from observed task outcomes.

    This is an engineering efficiency metric, not a claim about intelligence.
    Missing measurements receive zero rather than guessed credit.
    """

    def __init__(self, path: Path) -> None:
        self.path = Path(path)

    def record(self, *, task_type: str, provider: str, success: bool, quality: float,
               latency_seconds: float, compute_units: float, monetary_cost_usd: float = 0.0) -> EfficiencyRecord:
        if not 0.0 <= quality <= 1.0:
            raise ValueError("quality must be between 0 and 1")
        if latency_seconds < 0 or compute_units <= 0 or monetary_cost_usd < 0:
            raise ValueError("resource measurements must be non-negative and compute_units > 0")
        record = EfficiencyRecord(
            task_type=task_type,
            provider=provider,
            success=bool(success),
            quality=float(quality),
            latency_seconds=float(latency_seconds),
            compute_units=float(compute_units),
            monetary_cost_usd=float(monetary_cost_usd),
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(asdict(record), sort_keys=True) + "\n")
        return record

    def records(self) -> list[EfficiencyRecord]:
        if not self.path.exists():
            return []
        out: list[EfficiencyRecord] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            try:
                out.append(EfficiencyRecord(**json.loads(line)))
            except Exception:
                continue
        return out

    def report(self) -> dict:
        rows = self.records()
        if not rows:
            return {
                "score": 0,
                "max_score": 100,
                "status": "unmeasured",
                "samples": 0,
                "capability_per_compute": 0.0,
                "success_rate": 0.0,
                "average_quality": 0.0,
                "average_latency_seconds": None,
                "average_cost_usd": None,
                "interpretation": "No efficiency credit until real task measurements exist.",
            }
        samples = len(rows)
        success_rate = sum(1 for r in rows if r.success) / samples
        average_quality = sum(r.quality for r in rows) / samples
        total_compute = sum(r.compute_units for r in rows)
        capability_per_compute = sum(r.quality * (1.0 if r.success else 0.0) for r in rows) / total_compute
        avg_latency = sum(r.latency_seconds for r in rows) / samples
        avg_cost = sum(r.monetary_cost_usd for r in rows) / samples
        # Conservative internal index: quality and reliability dominate; compute
        # efficiency adds limited credit. This is not a frontier comparison.
        score = round(min(100.0, 50 * average_quality + 30 * success_rate + 20 * min(1.0, capability_per_compute)))
        return {
            "score": score,
            "max_score": 100,
            "status": "measured",
            "samples": samples,
            "capability_per_compute": round(capability_per_compute, 6),
            "success_rate": round(success_rate, 4),
            "average_quality": round(average_quality, 4),
            "average_latency_seconds": round(avg_latency, 4),
            "average_cost_usd": round(avg_cost, 6),
            "interpretation": "Measured engineering efficiency; higher means more successful quality per recorded resource unit.",
        }
