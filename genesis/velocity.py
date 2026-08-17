from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path


@dataclass(frozen=True)
class VelocityTargets:
    min_validated_updates_24h: int = 4
    max_latest_update_age_minutes: float = 360.0
    max_mean_inter_update_minutes: float = 240.0


class GeneVelocity:
    """Measure Gene's validated evolution speed from blockchain evidence.

    Velocity is intentionally based on independently validated updates rather than
    raw commits. Faster unsafe or unvalidated changes do not improve this score.
    """

    def __init__(self, root: Path, targets: VelocityTargets | None = None) -> None:
        self.root = root.resolve()
        self.targets = targets or VelocityTargets()
        self.ledger = self.root / "network" / "blockchain.jsonl"

    @staticmethod
    def _parse_timestamp(value: str) -> datetime | None:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except (TypeError, ValueError):
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

    def _validated_timestamps(self) -> list[datetime]:
        if not self.ledger.is_file():
            return []
        timestamps: list[datetime] = []
        for line in self.ledger.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            if item.get("payload_type") != "validated_update":
                continue
            timestamp = self._parse_timestamp(str(item.get("timestamp", "")))
            if timestamp is not None:
                timestamps.append(timestamp)
        return sorted(timestamps)

    def report(self, *, now: datetime | None = None) -> dict:
        now = now or datetime.now(timezone.utc)
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        now = now.astimezone(timezone.utc)
        timestamps = self._validated_timestamps()
        cutoff = now - timedelta(hours=24)
        recent = [item for item in timestamps if cutoff <= item <= now]

        intervals = [
            (right - left).total_seconds() / 60.0
            for left, right in zip(recent, recent[1:])
            if right >= left
        ]
        mean_interval = sum(intervals) / len(intervals) if intervals else None
        latest_age = (now - timestamps[-1]).total_seconds() / 60.0 if timestamps else None

        failures: list[str] = []
        if len(recent) < self.targets.min_validated_updates_24h:
            failures.append("validated_updates_24h_below_target")
        if latest_age is None or latest_age > self.targets.max_latest_update_age_minutes:
            failures.append("latest_validated_update_too_old")
        if mean_interval is None or mean_interval > self.targets.max_mean_inter_update_minutes:
            failures.append("validated_cycle_time_above_target")

        return {
            "status": "accelerate" if failures else "on_target",
            "validated_updates_24h": len(recent),
            "latest_validated_update_age_minutes": round(latest_age, 2) if latest_age is not None else None,
            "mean_inter_update_minutes_24h": round(mean_interval, 2) if mean_interval is not None else None,
            "targets": {
                "min_validated_updates_24h": self.targets.min_validated_updates_24h,
                "max_latest_update_age_minutes": self.targets.max_latest_update_age_minutes,
                "max_mean_inter_update_minutes": self.targets.max_mean_inter_update_minutes,
            },
            "gaps": failures,
            "principle": "Optimize validated capability growth; unvalidated speed receives no credit.",
        }

    def improvement_objective(self, *, now: datetime | None = None) -> str | None:
        report = self.report(now=now)
        if report["status"] == "on_target":
            return None
        gaps = ", ".join(report["gaps"])
        return (
            "Increase Gene's validated development velocity without weakening tests, security, provenance, "
            "independent validator quorum, owner authorization, or Constitution constraints. "
            f"Current velocity gaps: {gaps}. Prefer changes that reduce gap-to-task, task-to-candidate, "
            "candidate-to-validation, benchmark-refresh, and provider-evaluation latency while improving real capability."
        )
