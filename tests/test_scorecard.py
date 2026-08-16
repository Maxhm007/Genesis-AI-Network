from pathlib import Path

from genesis.scorecard import GenesisScorecard


def test_scorecard_separates_capability_efficiency_and_mission(tmp_path: Path):
    (tmp_path / "genesis").mkdir()
    (tmp_path / "config").mkdir()
    (tmp_path / "runtime").mkdir()
    report = GenesisScorecard(tmp_path).report()
    assert "ai_capability_score" in report
    assert "efficiency_score" in report
    assert "immortality_research_progress_score" in report
    assert report["efficiency_score"]["score"] == 0
    assert "not a percentage" in report["immortality_research_progress_score"]["interpretation"]
