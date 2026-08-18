from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .autonomy_proof import AutonomyProofLedger


@dataclass(frozen=True)
class VelocityTargets:
    min_validated_updates_24h: int = 4
    max_latest_update_age_minutes: float = 360.0
    max_mean_inter_update_minutes: float = 240.0


class GeneVelocity:
    """Measure validated evolution speed; unsafe/unvalidated changes earn no credit."""

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
        intervals = [(right-left).total_seconds()/60.0 for left, right in zip(recent, recent[1:]) if right >= left]
        mean_interval = sum(intervals) / len(intervals) if intervals else None
        latest_age = (now - timestamps[-1]).total_seconds()/60.0 if timestamps else None
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
            "Increase Gene's validated development velocity without weakening tests, security, provenance, independent validator "
            "quorum, owner authorization, or Constitution constraints. "
            f"Current velocity gaps: {gaps}. Prefer changes that reduce gap-to-task, task-to-candidate, candidate-to-validation, "
            "benchmark-refresh, and provider-evaluation latency while improving real capability."
        )


class AdaptiveVelocityController:
    """Safely increases development throughput as Genesis proves reliable autonomy."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root).resolve()
        self.proof = AutonomyProofLedger(self.root)

    def policy(self) -> dict:
        rows = [r for r in self.proof.events(200) if r.get("stage") == "cycle_complete"][-20:]
        total = len(rows)
        successes = [r for r in rows if r.get("outcome") == "success"]
        autonomous = [r for r in rows if r.get("classification") == "genesis_autonomous"]
        risky = [r for r in rows if r.get("outcome") in {"security_rejected", "rollback", "owner_escalation", "failed"}]
        success_rate = len(successes) / total if total else 0.0
        autonomy_rate = len(autonomous) / total if total else 0.0

        level = 1
        if total >= 3 and success_rate >= 0.80 and autonomy_rate >= 0.60:
            level = 2
        if total >= 6 and success_rate >= 0.85 and autonomy_rate >= 0.70:
            level = 3
        if total >= 10 and success_rate >= 0.90 and autonomy_rate >= 0.80:
            level = 4
        if total >= 15 and success_rate >= 0.95 and autonomy_rate >= 0.90:
            level = 5
        if risky:
            level = max(1, level - min(2, len(risky)))

        burst_by_level = {1: 1, 2: 2, 3: 3, 4: 4, 5: 5}
        parallel_by_level = {1: 1, 2: 1, 3: 2, 4: 3, 5: 4}
        interval_multiplier = {1: 1.0, 2: 0.8, 3: 0.65, 4: 0.5, 5: 0.35}
        return {
            "acceleration_level": level,
            "recent_cycles": total,
            "success_rate": round(success_rate, 4),
            "autonomy_rate": round(autonomy_rate, 4),
            "recent_risk_events": len(risky),
            "max_development_burst": burst_by_level[level],
            "recommended_parallel_candidates": parallel_by_level[level],
            "cycle_interval_multiplier": interval_multiplier[level],
            "can_accelerate": len(risky) == 0 and level > 1,
            "rule": "Speed increases only after repeated validated autonomous success and falls immediately after risk/failure evidence.",
        }
