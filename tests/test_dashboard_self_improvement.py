from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DASHBOARD = ROOT / "web" / "dashboard.html"


def test_dashboard_shows_promoted_genesis_self_improvements():
    dashboard = DASHBOARD.read_text(encoding="utf-8")

    assert 'id="self-improvement"' in dashboard
    assert "Self Improvement" in dashboard
    assert "Genesis self-development candidate:" in dashboard
    assert "/commits?author=genesis-ai&per_page=" in dashboard
    assert "Promoted to main" in dashboard
    assert "Genesis-authored" in dashboard
    assert "Candidate-only and human-authored changes are excluded" in dashboard


def test_dashboard_self_improvement_feed_has_safe_fallback():
    dashboard = DASHBOARD.read_text(encoding="utf-8")

    assert "genesis/learned_capabilities.py" in dashboard
    assert "learnedFallback" in dashboard
    assert "authorship is not asserted in fallback mode" in dashboard
    assert "const esc=" in dashboard
    assert "encodeURIComponent(item.sha)" in dashboard
    assert "setInterval(loadSelfImprovements,300000)" in dashboard
