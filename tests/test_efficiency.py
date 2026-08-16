from pathlib import Path

from genesis.efficiency import EfficiencyTracker


def test_efficiency_is_unmeasured_without_evidence(tmp_path: Path):
    report = EfficiencyTracker(tmp_path / "efficiency.jsonl").report()
    assert report["score"] == 0
    assert report["status"] == "unmeasured"


def test_efficiency_uses_observed_outcomes(tmp_path: Path):
    tracker = EfficiencyTracker(tmp_path / "efficiency.jsonl")
    tracker.record(task_type="coding", provider="small", success=True, quality=0.9, latency_seconds=1.2, compute_units=1.0)
    tracker.record(task_type="research", provider="small", success=True, quality=0.8, latency_seconds=2.0, compute_units=1.0)
    report = tracker.report()
    assert report["status"] == "measured"
    assert report["samples"] == 2
    assert report["capability_per_compute"] > 0
    assert 0 < report["score"] <= 100
