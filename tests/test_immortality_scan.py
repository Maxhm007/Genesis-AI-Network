from pathlib import Path

from genesis.immortality_scan import ImmortalityScanner, ScanItem


def test_direct_longevity_signal_is_high_priority(tmp_path: Path):
    scanner = ImmortalityScanner(tmp_path)
    item = ScanItem(
        source="test",
        title="Epigenetic reprogramming improves healthspan in aging cells",
        url="https://example.invalid/1",
        published=None,
        summary="regenerative medicine and cellular rejuvenation",
    )
    result = scanner.assess(item)
    assert result.relevance_score >= 8
    assert result.action == "create_priority_research_task"
    assert "biology_medicine" in result.domains


def test_cross_domain_signal_is_considered_without_forcing_claim(tmp_path: Path):
    scanner = ImmortalityScanner(tmp_path)
    item = ScanItem(
        source="test",
        title="New battery material improves long-duration robotics",
        url="https://example.invalid/2",
        published=None,
        summary="energy storage and robot systems",
    )
    result = scanner.assess(item)
    assert result.relevance_score >= 2
    assert "energy_materials" in result.domains
    assert "ai_computing" in result.domains


def test_unrelated_signal_does_not_get_fake_immortality_link(tmp_path: Path):
    scanner = ImmortalityScanner(tmp_path)
    item = ScanItem(
        source="test",
        title="Local art exhibition opens Saturday",
        url="https://example.invalid/3",
        published=None,
        summary="paintings and sculpture",
    )
    result = scanner.assess(item)
    assert result.relevance_score == 0
    assert result.relevance == "unknown"
    assert result.action == "do_not_force_connection"
