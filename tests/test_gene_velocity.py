from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from genesis.velocity import GeneVelocity, VelocityTargets


def _write_ledger(root: Path, timestamps: list[datetime]) -> None:
    path = root / "network" / "blockchain.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = []
    for index, timestamp in enumerate(timestamps):
        lines.append(json.dumps({
            "height": index,
            "payload_type": "validated_update",
            "timestamp": timestamp.astimezone(timezone.utc).isoformat(),
            "validated_commit": f"commit-{index}",
        }))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_velocity_on_target_counts_only_validated_updates(tmp_path: Path) -> None:
    now = datetime(2026, 8, 17, 12, tzinfo=timezone.utc)
    stamps = [
        now - timedelta(hours=6),
        now - timedelta(hours=4),
        now - timedelta(hours=2),
        now - timedelta(minutes=30),
    ]
    _write_ledger(tmp_path, stamps)
    report = GeneVelocity(tmp_path).report(now=now)
    assert report["status"] == "on_target"
    assert report["validated_updates_24h"] == 4
    assert report["gaps"] == []


def test_velocity_accelerates_when_validated_cycle_is_stale(tmp_path: Path) -> None:
    now = datetime(2026, 8, 17, 12, tzinfo=timezone.utc)
    _write_ledger(tmp_path, [now - timedelta(hours=20), now - timedelta(hours=14)])
    report = GeneVelocity(tmp_path).report(now=now)
    assert report["status"] == "accelerate"
    assert "validated_updates_24h_below_target" in report["gaps"]
    assert "latest_validated_update_too_old" in report["gaps"]
    assert GeneVelocity(tmp_path).improvement_objective(now=now) is not None


def test_velocity_does_not_reward_missing_validation_evidence(tmp_path: Path) -> None:
    now = datetime(2026, 8, 17, 12, tzinfo=timezone.utc)
    path = tmp_path / "network" / "blockchain.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"payload_type": "raw_commit", "timestamp": now.isoformat()}) + "\n", encoding="utf-8")
    report = GeneVelocity(tmp_path, VelocityTargets(min_validated_updates_24h=1)).report(now=now)
    assert report["validated_updates_24h"] == 0
    assert report["status"] == "accelerate"
