from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DASHBOARD = ROOT / "web" / "dashboard.html"


def test_dashboard_shows_promoted_genesis_self_improvements():
    dashboard = DASHBOARD.read_text(encoding="utf-8")

    assert 'id="self-improvement"' in dashboard
    assert "Self Improvement" in dashboard
    assert "Promoted capabilities" in dashboard
    assert "genesis/learned_capabilities.py" in dashboard
    assert "Promoted to main" in dashboard
    assert "Learned capability" in dashboard
    assert "Candidate-only work and human-authored fixes are excluded" in dashboard


def test_dashboard_self_improvement_feed_reads_promoted_registry_safely():
    dashboard = DASHBOARD.read_text(encoding="utf-8")

    assert "const LEARNED_RAW=" in dashboard
    assert "learnedCapabilityNames" in dashboard
    assert "renderLearnedCapabilities" in dashboard
    assert "read <code>genesis/learned_capabilities.py</code> directly from <code>main</code>" in dashboard
    assert "/commits?author=genesis-ai&per_page=" not in dashboard
    assert "const esc=" in dashboard
    assert "setInterval(loadSelfImprovements,300000)" in dashboard
