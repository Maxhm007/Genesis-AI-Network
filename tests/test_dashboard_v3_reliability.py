import json
from pathlib import Path

import pytest

from scripts import dashboard_v3_patch as v3
from scripts import render_static_dashboard as static
from scripts import validate_dashboard_artifact as artifact


def _payload() -> dict:
    return {
        "generated_at": "2026-08-22T09:00:00Z",
        "ai_capability": 37,
        "verified_autonomy": {"autonomous_promotions": 1, "assisted_promotions": 2, "owner_promotions": 3},
        "network": {"available_peers": 2, "total_peers": 3, "peer_availability": 67, "quorum": "2/3"},
        "issues": {"open": 1, "blocked": 0, "resolved": 2},
        "tasks": {"new": 2, "running": 1, "complete": 3, "quarantined": 4},
        "genes": {"0": {"gene": "Gene 0", "health": {"state": "healthy"}}},
        "targets": [{"title": "AI capability below target", "severity": "high", "status": "open", "module": "genesis.ai_score", "generation": 20}],
        "recent_activity": [{"message": "Genesis improvement", "date": "2026-08-22T08:50:00Z", "author": "Genesis", "url": "https://example.test/a"}],
        "nodes": [{"node": 0, "state": "healthy", "workflow": "Gene Pulse", "updated_at": "2026-08-22T08:59:00Z", "url": "https://example.test/node"}],
        "candidate_prs": [{"number": 10, "title": "Capability candidate", "state": "open", "merged": False, "head": "genesis/candidate-10", "updated_at": "2026-08-22T08:55:00Z", "url": "https://example.test/pr"}],
        "hourly_report": {"text": "Genesis Hourly Operations Report\nAI Capability: 37/100"},
        "capability_evolution": {
            "coverage": {"measured": 1, "total": 6, "below_reference": 1, "unmeasured": 5},
            "growth": {"active": 1, "new_capability_tasks": 1},
            "strategy": {"quarantined_total": 4, "directives": 1},
            "impact": {"improved": 1},
            "gaps": [{"benchmark_id": "swe_bench_pro", "status": "measured_below_reference", "family": "software_engineering", "capability_key": "software_engineering", "target_path": "genesis/coding.py", "actual_score": 40, "reference_score": 80, "unit": "score"}],
            "active_growth_tasks": [{"capability_key": "software_engineering", "state": "running", "benchmark_id": "swe_bench_pro", "generation": 2, "target_path": "genesis/coding.py"}],
            "strategy_directives": ["Change implementation strategy after repeated quarantine."],
            "impact_assessments": [{"benchmark_id": "swe_bench_pro", "status": "improved", "baseline_score": 35, "current_score": 40, "delta": 5}],
        },
        "self_development_evaluation": {
            "strict_verified_cycles": 1,
            "historical_autonomous_main_evidence": 6,
            "genesis_authored_main_commits": 4,
            "attribution": {"genesis_autonomous": 1, "assisted": 2, "owner": 3},
            "recent_genesis_authored_main": [{"title": "Runtime health snapshot", "author": "Genesis AI", "authored_at": "2026-08-16T00:00:00Z", "sha": "abcdef123456", "url": "https://example.test/commit"}],
            "recent_improvements": [{"number": 11, "title": "Autonomous candidate", "attribution": "genesis_autonomous", "improvement": "Improved health handling", "merged_at": "2026-08-17T00:00:00Z", "url": "https://example.test/promotion"}],
            "definition": "Strict proof requires initiation, validation and promotion.",
        },
    }


def test_sections_have_static_content_for_every_major_view():
    rendered = static.sections(_payload())
    for key in ("focus", "latestActivity", "activity", "gapList", "growthList", "strategyList", "impactList", "targets", "taskStats", "peerGrid", "prs", "autoMainHistory", "autoPromotionHistory", "autoDefinition"):
        assert rendered[key].strip()
    assert "swe_bench_pro" in rendered["gapList"]
    assert "AI capability below target" in rendered["targets"]
    assert "Runtime health snapshot" in rendered["autoMainHistory"]


def test_v3_patch_adds_build_meta_and_mobile_reliability_css(tmp_path: Path):
    page = tmp_path / "index.html"
    page.write_text('<html><head><style></style></head><body><div class="brand"><span>Command Center · Evidence v2</span></div><div id="updated" class="updated">Loading…</div></body></html>', encoding="utf-8")
    v3.patch(page)
    html = page.read_text(encoding="utf-8")
    assert "genesis-dashboard-v3" in html
    assert 'id="buildMeta"' in html
    assert "Evidence v3" in html
    assert "overflow-x:auto" in html


def _artifact_page() -> str:
    navs = "".join(f'<a data-view="{name}" href="#view-{name}">{name}</a>' for name in ("overview", "evolution", "autonomy", "issues", "tasks", "peers", "activity", "prs", "reports"))
    views = "".join(f'<section class="view" id="view-{name}">ok</section>' for name in ("overview", "evolution", "autonomy", "issues", "tasks", "peers", "activity", "prs", "reports"))
    ids = {
        "heroTitle": "Gene 0 · healthy",
        "ai": "37/100",
        "coverage": "1/6",
        "autonomy": "1",
        "focus": "focus evidence",
        "gapList": "benchmark evidence",
        "targets": "issue evidence",
        "taskStats": "task evidence",
        "peerGrid": "peer evidence",
        "activity": "activity evidence",
        "prs": "PR evidence",
        "report": "hourly report",
        "buildMeta": "Build abcdef1234 · run 123",
    }
    blocks = "".join(f'<div id="{key}">{value}</div>' for key, value in ids.items())
    return f'<html><head><style>/* genesis-no-js-navigation */ /* genesis-dashboard-v3 */</style></head><body><nav>{navs}</nav>{blocks}{views}</body></html>'


def test_artifact_validator_accepts_static_navigable_dashboard(tmp_path: Path):
    page = tmp_path / "index.html"
    page.write_text(_artifact_page(), encoding="utf-8")
    artifact.validate(page)


def test_artifact_validator_rejects_empty_tab_content(tmp_path: Path):
    page = tmp_path / "index.html"
    page.write_text(_artifact_page().replace("benchmark evidence", ""), encoding="utf-8")
    with pytest.raises(RuntimeError, match="gapList"):
        artifact.validate(page)


def test_pages_workflow_runs_v3_patch_static_render_and_artifact_validation_in_order():
    workflow = Path(".github/workflows/pages-status.yml").read_text(encoding="utf-8")
    order = [
        "python scripts/dashboard_navigation_fallback.py",
        "python scripts/dashboard_v3_patch.py",
        "python scripts/render_static_dashboard.py",
        "python scripts/validate_dashboard_js.py",
        "python scripts/validate_dashboard_artifact.py",
    ]
    positions = [workflow.index(item) for item in order]
    assert positions == sorted(positions)
