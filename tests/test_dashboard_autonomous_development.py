import json
from pathlib import Path

from scripts import self_evaluation_dashboard as dashboard


def test_genesis_authored_main_commits_are_historical_not_strict_credit():
    commits = [
        {
            "sha": "abc123",
            "html_url": "https://example.test/commit/abc123",
            "commit": {
                "message": "Genesis self-development candidate: Add runtime health snapshot helper",
                "author": {"name": "Genesis AI", "date": "2026-08-16T14:46:19Z"},
            },
        },
        {
            "sha": "human123",
            "html_url": "https://example.test/commit/human123",
            "commit": {
                "message": "Update documentation",
                "author": {"name": "Human", "date": "2026-08-16T15:00:00Z"},
            },
        },
    ]

    rows = dashboard.genesis_authored_main_commits(commits)
    assert len(rows) == 1
    assert rows[0]["title"] == "Add runtime health snapshot helper"
    assert rows[0]["credit"] == "historical_genesis_authored_main"
    assert "default-branch history" in rows[0]["evidence"]


def test_enrich_status_keeps_strict_ledger_separate_from_historical_main_commits(tmp_path, monkeypatch):
    status = tmp_path / "status.json"
    status.write_text(
        json.dumps(
            {
                "verified_autonomy": {
                    "autonomous_promotions": 2,
                    "assisted_promotions": 1,
                    "owner_promotions": 1,
                },
                "genes": {"0": {"kpis": {}}},
                "network": {},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(dashboard, "STATUS", status)

    history = [
        {
            "number": 7,
            "title": "Autonomous change",
            "improvement": "change",
            "head": "genesis/candidate-test",
            "lane": "normal",
            "merged_at": "2026-08-22T00:00:00Z",
            "url": "https://example.test/pr/7",
            "attribution": "genesis_autonomous",
            "classification": "genesis_autonomous",
            "evidence": "Genesis autonomous provenance",
        },
        {
            "number": 8,
            "title": "Assisted change",
            "improvement": "change",
            "head": "genesis/candidate-assisted",
            "lane": "normal",
            "merged_at": "2026-08-22T01:00:00Z",
            "url": "https://example.test/pr/8",
            "attribution": "assisted",
            "classification": "assisted",
            "evidence": "assisted/manual provenance",
        },
    ]
    authored = [
        {
            "sha": "abc",
            "title": "Health helper",
            "message": "Genesis self-development candidate: Health helper",
            "authored_at": "2026-08-16T00:00:00Z",
            "author": "Genesis AI",
            "url": "https://example.test/commit/abc",
            "evidence": "Genesis AI authored self-development commit present in default-branch history",
            "credit": "historical_genesis_authored_main",
        }
    ]

    dashboard.enrich_status(history, authored)
    payload = json.loads(status.read_text(encoding="utf-8"))
    evaluation = payload["self_development_evaluation"]
    assert evaluation["strict_verified_cycles"] == 2
    assert evaluation["autonomous_pr_promotions"] == 1
    assert evaluation["genesis_authored_main_commits"] == 1
    assert evaluation["attribution"]["assisted"] == 1
    assert "older commits may predate complete ledger provenance" in evaluation["definition"]


def test_patch_dashboard_adds_autonomous_development_view_to_command_center_v2(tmp_path, monkeypatch):
    page = tmp_path / "index.html"
    page.write_text(
        '''<html><body>
<nav><button data-view="evolution">Capability Evolution</button><button data-view="issues">Issues</button></nav>
<section class="view" id="view-evolution"></section>
<section class="view" id="view-issues"></section>
<script>
const names={overview:['Overview','x'],evolution:['Capability Evolution','Benchmark-driven learning and measured improvement'],issues:['Issues','y']};
function render(){const auto={assisted_promotions:0,owner_promotions:0};$('#autonomyCap').textContent=`Assisted ${auto.assisted_promotions??0} · Owner ${auto.owner_promotions??0}`;}
</script></body></html>''',
        encoding="utf-8",
    )
    monkeypatch.setattr(dashboard, "DASHBOARD", page)

    dashboard.patch_dashboard()
    first = page.read_text(encoding="utf-8")
    assert 'data-view="autonomy"' in first
    assert 'id="view-autonomy"' in first
    assert "Strict Verified Cycles" in first
    assert "Genesis-Authored on Main" in first
    assert "autonomy:['Autonomous Development'" in first
    assert "recent_genesis_authored_main" in first

    dashboard.patch_dashboard()
    second = page.read_text(encoding="utf-8")
    assert second.count('data-view="autonomy"') == 1
    assert second.count('id="view-autonomy"') == 1
