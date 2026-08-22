import json
from pathlib import Path

import pytest

from scripts import autonomy_history_backfill as backfill


ROOT = Path(__file__).resolve().parents[1]


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
            "author": "Genesis AI",
            "committer": "Genesis AI",
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
    assert evaluation["history_source"] == "full_local_git_log_head"
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


def test_parse_git_history_finds_trusted_genesis_actors_only():
    sep = "\x1f"
    history = "\n".join(
        [
            sep.join(
                [
                    "abc",
                    "Genesis AI",
                    "genesis-ai@users.noreply.github.com",
                    "Genesis AI",
                    "genesis-ai@users.noreply.github.com",
                    "2026-08-16T14:46:19+00:00",
                    "Genesis self-development candidate: Add runtime health snapshot helper",
                ]
            ),
            sep.join(
                [
                    "def",
                    "Genesis Autonomy Trial",
                    "actions@github.com",
                    "Genesis Promotion Stager",
                    "actions@github.com",
                    "2026-08-17T22:45:05+00:00",
                    "Genesis self-development candidate: Fix health snapshot status handling",
                ]
            ),
            sep.join(
                [
                    "human",
                    "Human",
                    "human@example.com",
                    "Human",
                    "human@example.com",
                    "2026-08-18T00:00:00+00:00",
                    "Genesis self-development candidate: Pretend autonomous change",
                ]
            ),
        ]
    )

    rows, candidates = backfill.parse_git_history(history)

    assert candidates == 3
    assert [row["sha"] for row in rows] == ["def", "abc"]
    assert {row["provenance"] for row in rows} == {"genesis_ai_authored", "autonomy_trial_promoted"}


def test_scan_rejects_shallow_checkout(monkeypatch):
    monkeypatch.setattr(backfill, "_run_git", lambda args, root: "true" if args[0] == "rev-parse" else "")
    with pytest.raises(RuntimeError, match="full git checkout"):
        backfill.scan_local_main_history(Path("."))


def test_scan_refuses_false_zero_when_signatures_exist(monkeypatch):
    sep = "\x1f"
    human_only = sep.join(
        [
            "human",
            "Human",
            "human@example.com",
            "Human",
            "human@example.com",
            "2026-08-18T00:00:00+00:00",
            "Genesis self-development candidate: Pretend autonomous change",
        ]
    )

    def fake_git(args, root):
        if args[0] == "rev-parse":
            return "false"
        return human_only

    monkeypatch.setattr(backfill, "_run_git", fake_git)
    with pytest.raises(RuntimeError, match="refusing false zero evidence"):
        backfill.scan_local_main_history(Path("."))


def test_pages_workflow_checks_out_full_history_before_backfill():
    workflow = (ROOT / ".github" / "workflows" / "pages-status.yml").read_text(encoding="utf-8")
    assert "fetch-depth: 0" in workflow
    assert "python scripts/autonomy_history_backfill.py" in workflow
