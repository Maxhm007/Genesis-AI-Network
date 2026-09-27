from datetime import datetime, timezone

import scripts.capability_issue_priority_dispatch as module


def _issue(number, *, body="", labels=(), state="open", created_at="2026-09-20T00:00:00Z"):
    return {
        "number": number,
        "body": body,
        "state": state,
        "created_at": created_at,
        "labels": [{"name": label} for label in labels],
    }


def test_dependency_unlock_counts_tracks_live_parents_and_releases():
    issues = [
        _issue(100),
        _issue(101),
        _issue(200, body="<!-- genesis-capability-work:abc -->"),
    ]
    comments = {
        100: [{"body": "<!-- genesis-capability-dependency:200 -->"}],
        101: [
            {"body": "<!-- genesis-capability-dependency:200 -->"},
            {"body": "<!-- genesis-agentic-capability-release:200 -->"},
        ],
        200: [],
    }

    assert module.dependency_unlock_counts(issues, comments) == {200: 1}


def test_score_uses_dependency_unlock_count():
    issue = _issue(
        200,
        body="<!-- genesis-capability-work:abc -->",
        labels=("genesis-capability-gap",),
    )
    now = datetime(2026, 9, 25, tzinfo=timezone.utc)

    low = module.score_issue(issue, [], now=now, blocked_issues=0)
    high = module.score_issue(issue, [], now=now, blocked_issues=4)

    assert high["score"] > low["score"]
    assert high["blocked_issues"] == 4
    assert high["breakdown"]["blocked_issues"] > low["breakdown"]["blocked_issues"]
