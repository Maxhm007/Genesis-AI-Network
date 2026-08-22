import json
from pathlib import Path

from scripts import render_static_dashboard as static


def _page(include_autonomy: bool = True) -> str:
    ids = [
        ("updated", "Loading…"),
        ("sideUpdated", "Waiting for data…"),
        ("heroTitle", "Loading Genesis…"),
        ("heroText", "Reading the latest authenticated evidence."),
        ("heroAuto", "—"),
        ("ai", "—"),
        ("coverage", "—"),
        ("coverageCap", "Validated / total frontier families"),
        ("growth", "—"),
        ("quarantined", "—"),
        ("strategyCap", "Repeated failures analyzed"),
        ("autonomy", "—"),
        ("autonomyCap", "Promotion proof ledger"),
        ("peers", "—"),
        ("peersCap", "Network availability"),
        ("evMeasured", "—"),
        ("evBelow", "—"),
        ("evUnmeasured", "—"),
        ("evNew", "—"),
        ("evStrategy", "—"),
        ("evImproved", "—"),
        ("iOpen", "—"),
        ("iBlocked", "—"),
        ("iResolved", "—"),
    ]
    if include_autonomy:
        ids.extend(
            [
                ("autoStrict", "—"),
                ("autoPr", "—"),
                ("autoMain", "—"),
                ("autoOther", "—"),
                ("autoOtherCap", "Kept outside autonomous credit"),
            ]
        )
    body = "".join(f'<div id="{element_id}">{text}</div>' for element_id, text in ids)
    return f'<html><body>{body}<i id="aiBar"></i></body></html>'


def _payload() -> dict:
    return {
        "generated_at": "2026-08-22T08:35:00Z",
        "ai_capability": 37,
        "verified_autonomy": {"autonomous_promotions": 2, "assisted_promotions": 61, "owner_promotions": 6},
        "network": {"available_peers": 2, "total_peers": 3, "peer_availability": 67, "quorum": "2/3"},
        "issues": {"open": 1, "blocked": 0, "resolved": 3},
        "tasks": {"quarantined": 11},
        "genes": {"0": {"gene": "Gene 0", "health": {"state": "healthy"}}},
        "capability_evolution": {
            "coverage": {"measured": 1, "total": 6, "below_reference": 1, "unmeasured": 5},
            "growth": {"active": 1, "new_capability_tasks": 2},
            "strategy": {"quarantined_total": 11, "directives": 1},
            "impact": {"improved": 1},
            "gaps": [
                {
                    "benchmark_id": "swe_bench_pro",
                    "status": "measured_below_reference",
                    "capability_key": "software_engineering",
                }
            ],
        },
        "self_development_evaluation": {
            "strict_verified_cycles": 2,
            "historical_autonomous_main_evidence": 6,
            "genesis_authored_main_commits": 4,
            "attribution": {"assisted": 61, "owner": 6, "genesis_autonomous": 2},
        },
    }


def test_static_first_paint_replaces_loading_and_headline_placeholders(tmp_path: Path):
    status = tmp_path / "status.json"
    page = tmp_path / "index.html"
    status.write_text(json.dumps(_payload()), encoding="utf-8")
    page.write_text(_page(), encoding="utf-8")

    static.render_static(status, page)
    html = page.read_text(encoding="utf-8")

    assert 'id="heroTitle">Gene 0 · healthy<' in html
    assert 'id="heroText">swe_bench_pro: measured below reference · capability software_engineering<' in html
    assert 'id="ai">37/100<' in html
    assert 'id="coverage">1/6<' in html
    assert 'id="autonomy">2<' in html
    assert 'id="autoPr">6<' in html
    assert 'id="autoMain">4<' in html
    assert 'id="aiBar" style="width:37%"' in html
    assert "Loading Genesis…" not in html


def test_static_first_paint_works_without_optional_autonomy_view(tmp_path: Path):
    status = tmp_path / "status.json"
    page = tmp_path / "index.html"
    status.write_text(json.dumps(_payload()), encoding="utf-8")
    page.write_text(_page(include_autonomy=False), encoding="utf-8")

    static.render_static(status, page)
    html = page.read_text(encoding="utf-8")
    assert 'id="ai">37/100<' in html
    assert "Loading Genesis…" not in html


def test_static_first_paint_is_idempotent(tmp_path: Path):
    status = tmp_path / "status.json"
    page = tmp_path / "index.html"
    status.write_text(json.dumps(_payload()), encoding="utf-8")
    page.write_text(_page(), encoding="utf-8")

    static.render_static(status, page)
    first = page.read_text(encoding="utf-8")
    static.render_static(status, page)
    second = page.read_text(encoding="utf-8")
    assert first == second


def test_pages_workflow_renders_static_snapshot_before_js_validation():
    workflow = Path(".github/workflows/pages-status.yml").read_text(encoding="utf-8")
    assert "python scripts/render_static_dashboard.py" in workflow
    assert workflow.index("python scripts/embed_dashboard_status.py") < workflow.index("python scripts/render_static_dashboard.py")
    assert workflow.index("python scripts/render_static_dashboard.py") < workflow.index("python scripts/validate_dashboard_js.py")
