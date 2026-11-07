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


def test_assess_handles_varied_scan_items_without_swallowing_errors(tmp_path: Path):
    scanner = ImmortalityScanner(tmp_path)
    cases = [
        ("Longevity and healthspan in aging cells", "regenerative medicine", "direct_or_high"),
        ("Battery systems for robots", "energy storage", "speculative_or_weak"),
        ("Gallery opening", "paintings", "unknown"),
    ]
    for title, summary, expected in cases:
        assessment = scanner.assess(ScanItem("sample", title, "https://example.invalid", None, summary))
        assert assessment.relevance == expected
    # Bad inputs must not be quietly interpreted as a valid low-priority signal.
    import pytest

    with pytest.raises(AttributeError):
        scanner.assess(None)


def test_scan_records_expected_external_failures(tmp_path: Path, monkeypatch):
    import json
    import urllib.error

    scanner = ImmortalityScanner(tmp_path)
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "immortality_sources.json").write_text(
        json.dumps({"rss": [{"name": "RSS", "url": "https://example.invalid/feed"}]}),
        encoding="utf-8",
    )
    monkeypatch.setattr(scanner.research, "longevity_scan", lambda **kwargs: (_ for _ in ()).throw(urllib.error.URLError("offline")))
    monkeypatch.setattr(scanner, "fetch_rss", lambda *args: (_ for _ in ()).throw(TimeoutError("timeout")))
    output = scanner.scan()
    assert [entry["source"] for entry in output["errors"]] == ["Europe PMC", "RSS"]
    assert output["items"] == []


def test_scan_does_not_hide_programming_errors_in_research_or_rss(tmp_path: Path, monkeypatch):
    import json
    import pytest

    scanner = ImmortalityScanner(tmp_path)
    monkeypatch.setattr(scanner.research, "longevity_scan", lambda **kwargs: (_ for _ in ()).throw(TypeError("bad internal contract")))
    with pytest.raises(TypeError, match="bad internal contract"):
        scanner.scan()

    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "immortality_sources.json").write_text(
        json.dumps({"rss": [{"name": "RSS", "url": "https://example.invalid/feed"}]}),
        encoding="utf-8",
    )
    monkeypatch.setattr(scanner.research, "longevity_scan", lambda **kwargs: [])
    monkeypatch.setattr(scanner, "fetch_rss", lambda *args: (_ for _ in ()).throw(AssertionError("broken feed parser")))
    with pytest.raises(AssertionError, match="broken feed parser"):
        scanner.scan()
