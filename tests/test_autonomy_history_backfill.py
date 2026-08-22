import json
from pathlib import Path

from scripts import autonomy_history_backfill as backfill


def test_enrich_status_separates_strict_and_historical_evidence(tmp_path: Path):
    status = tmp_path / "status.json"
    status.write_text(
        json.dumps(
            {
                "verified_autonomy": {"autonomous_promotions": 0},
                "self_development_evaluation": {
                    "strict_verified_cycles": 0,
                    "autonomous_pr_promotions": 0,
                    "attribution": {"genesis_autonomous": 0, "assisted": 61, "owner": 6},
                },
                "genes": {"0": {"kpis": {}}},
                "network": {},
            }
        ),
        encoding="utf-8",
    )
    rows = [
        {
            "sha": "a1",
            "title": "Health helper",
            "authored_at": "2026-08-16T00:00:00Z",
            "author": "genesis-ai",
            "committer": "genesis-ai",
            "url": "https://example.test/a1",
            "provenance": "genesis_ai_authored",
            "evidence": "confirmed",
            "credit": "historical_autonomous_main_evidence",
        },
        {
            "sha": "a2",
            "title": "Health repair",
            "authored_at": "2026-08-17T00:00:00Z",
            "author": "Genesis Autonomy Trial",
            "committer": "Genesis Promotion Stager",
            "url": "https://example.test/a2",
            "provenance": "autonomy_trial_promoted",
            "evidence": "confirmed",
            "credit": "historical_autonomous_main_evidence",
        },
    ]

    backfill.enrich_status(rows, status)
    payload = json.loads(status.read_text(encoding="utf-8"))
    evaluation = payload["self_development_evaluation"]

    assert evaluation["strict_verified_cycles"] == 0
    assert evaluation["historical_autonomous_main_evidence"] == 2
    assert evaluation["genesis_authored_main_commits"] == 1
    assert evaluation["autonomy_trial_main_commits"] == 1
    assert evaluation["attribution"]["assisted"] == 61
    assert evaluation["attribution"]["owner"] == 6


def test_patch_dashboard_replaces_misleading_pr_only_card(tmp_path: Path):
    page = tmp_path / "index.html"
    page.write_text(
        """
        <div>Autonomous PR Promotions</div>
        <div>Merged candidate PRs carrying explicit Genesis autonomous provenance</div>
        <div>Genesis-Authored Main History</div>
        <script>$('#autoPr').textContent=sde.autonomous_pr_promotions??attr.genesis_autonomous??0;</script>
        No Genesis-authored self-development commit was found in default-branch history.
        """,
        encoding="utf-8",
    )

    backfill.patch_dashboard(page)
    html = page.read_text(encoding="utf-8")

    assert "Automated Main Evidence" in html
    assert "historical_autonomous_main_evidence" in html
    assert "Historical Autonomous Main Evidence" in html
    assert "No historical Genesis autonomous" in html


def test_search_self_development_commits_requires_main_ancestry_and_genesis_actor(monkeypatch):
    candidate = {
        "sha": "abc",
        "commit": {
            "message": "Genesis self-development candidate: Add runtime health snapshot helper",
            "author": {"name": "Genesis AI", "date": "2026-08-16T00:00:00Z"},
            "committer": {"name": "Genesis AI", "date": "2026-08-16T00:00:00Z"},
        },
        "author": {"login": "genesis-ai"},
        "committer": {"login": "genesis-ai"},
        "html_url": "https://example.test/abc",
    }

    def fake_safe_api(path, default):
        if path.startswith("/search/commits?"):
            return {"items": [{"sha": "abc"}]}
        if path.endswith("/commits/abc"):
            return candidate
        if "/compare/abc...main" in path:
            return {"status": "ahead", "merge_base_commit": {"sha": "abc"}}
        return default

    monkeypatch.setattr(backfill, "safe_api", fake_safe_api)
    rows = backfill.search_self_development_commits()

    assert len(rows) == 1
    assert rows[0]["sha"] == "abc"
    assert rows[0]["provenance"] == "genesis_ai_authored"
