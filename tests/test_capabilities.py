from pathlib import Path

from genesis.capabilities import CapabilityEvaluator
from genesis.providers import ProviderRegistry
from genesis.team import AITeam


def test_capability_report_is_bounded_and_explained(tmp_path: Path):
    (tmp_path / "genesis").mkdir()
    for name in ("communication.py", "selfdev.py", "promotion.py"):
        (tmp_path / "genesis" / name).write_text("# present\n", encoding="utf-8")
    providers = ProviderRegistry(include_bootstrap=True)
    team = AITeam(providers)
    report = CapabilityEvaluator(tmp_path, providers, team, test_probe=lambda: True).report()
    assert 0 <= report["score"] <= report["max_score"] == 100
    assert report["percent"] <= 100
    assert "not a measure of consciousness" in report["interpretation"]
    assert any(item["capability"] == "advanced_reasoning" for item in report["priority_gaps"])


def test_failed_test_probe_becomes_priority_gap(tmp_path: Path):
    (tmp_path / "genesis").mkdir()
    providers = ProviderRegistry(include_bootstrap=True)
    report = CapabilityEvaluator(tmp_path, providers, test_probe=lambda: False).report()
    health = next(item for item in report["results"] if item["capability"] == "software_health")
    assert health["status"] == "failing"
    assert health["score"] == 0
