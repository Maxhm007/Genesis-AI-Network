from datetime import datetime, timezone
from pathlib import Path

from genesis.ai_score import GenesisAIScorer
from genesis.providers import ProviderRegistry


class StrongProvider:
    name = "strong-provider"

    def available(self) -> bool:
        return True

    def reason(self, prompt: str) -> str:
        return "ok"


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
        "GDEN_SPEC.md",
    ):
        target = root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("# present\n", encoding="utf-8")


def test_ai_score_rewards_live_provider_and_fresh_research(tmp_path: Path):
    prepare_root(tmp_path)
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    (runtime / "immortality_scan.json").write_text(
        '{"created_at":"' + datetime.now(timezone.utc).isoformat() + '"}\n',
        encoding="utf-8",
    )
    registry = ProviderRegistry(include_bootstrap=True)
    registry.register(StrongProvider())
    report = GenesisAIScorer(tmp_path, registry).report()
    assert report["score"] >= 85
    assert report["urgency"] == "maintain_and_raise_benchmarks"


def test_ai_score_creates_update_pressure_when_provider_and_scan_missing(tmp_path: Path):
    prepare_root(tmp_path)
    report = GenesisAIScorer(tmp_path, ProviderRegistry(include_bootstrap=True)).report()
    assert report["score"] < 85
    assert report["urgency"] in {"improvement_required", "high_priority_update_required", "critical_update_required"}
    names = [item["name"] for item in report["priority_gaps"]]
    assert "reasoning" in names
    assert "research_freshness" in names
