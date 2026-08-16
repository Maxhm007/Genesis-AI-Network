from datetime import datetime, timezone
from pathlib import Path
import json

from genesis.ai_score import GenesisAIScorer
from genesis.providers import ProviderRegistry


def prepare_root(root: Path) -> None:
    (root / "genesis" / "modules").mkdir(parents=True)
    (root / "config").mkdir()
    for path in (
        "genesis/selfdev.py",
        "genesis/proactive.py",
        "genesis/research.py",
        "genesis/immortality_scan.py",
        "genesis/promotion.py",
        "genesis/gden.py",
        "genesis/peers.py",
        "genesis/modules/task_queue.py",
        "genesis/modules/benchmarking.py",
    ):
        target = root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("# present\n", encoding="utf-8")
    (root / "config" / "competitive_ai_reference.json").write_text(json.dumps({
        "as_of": "2026-08-16",
        "score_cap": 99,
        "benchmarks": [
            {"id": "reasoning", "reference_score": 80, "weight": 30},
            {"id": "coding", "reference_score": 70, "weight": 30},
        ],
    }), encoding="utf-8")


def test_unmeasured_frontier_ability_does_not_receive_fake_credit(tmp_path: Path):
    prepare_root(tmp_path)
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    (runtime / "immortality_scan.json").write_text(
        '{"created_at":"' + datetime.now(timezone.utc).isoformat() + '"}\n',
        encoding="utf-8",
    )
    report = GenesisAIScorer(tmp_path, ProviderRegistry(include_bootstrap=True)).report()
    frontier = next(item for item in report["dimensions"] if item["name"] == "frontier_competitive_benchmarks")
    assert frontier["score"] == 0
    assert report["score"] < 60
    assert "competitive" in report["urgency"]


def test_matching_frontier_results_earn_frontier_credit_but_never_100(tmp_path: Path):
    prepare_root(tmp_path)
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    (runtime / "immortality_scan.json").write_text(
        '{"created_at":"' + datetime.now(timezone.utc).isoformat() + '"}\n',
        encoding="utf-8",
    )
    (runtime / "competitive_benchmark_results.json").write_text(json.dumps({
        "benchmarks": {
            "reasoning": {"score": 80},
            "coding": {"score": 70},
        }
    }), encoding="utf-8")
    report = GenesisAIScorer(tmp_path, ProviderRegistry(include_bootstrap=True)).report()
    frontier = next(item for item in report["dimensions"] if item["name"] == "frontier_competitive_benchmarks")
    assert frontier["score"] == 60
    assert report["score"] == 97
    assert report["score"] <= 99


def test_consensus_can_raise_system_score_to_ultimate_cap_not_100(tmp_path: Path):
    prepare_root(tmp_path)
    (tmp_path / "genesis" / "gden_consensus.py").write_text("# present\n", encoding="utf-8")
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    (runtime / "immortality_scan.json").write_text(
        '{"created_at":"' + datetime.now(timezone.utc).isoformat() + '"}\n',
        encoding="utf-8",
    )
    (runtime / "competitive_benchmark_results.json").write_text(json.dumps({
        "benchmarks": {"reasoning": {"score": 90}, "coding": {"score": 80}}
    }), encoding="utf-8")
    report = GenesisAIScorer(tmp_path, ProviderRegistry(include_bootstrap=True)).report()
    assert report["score"] == 99
    assert report["max_score"] == 100
    assert report["urgency"] == "ultimate_target_threshold"
