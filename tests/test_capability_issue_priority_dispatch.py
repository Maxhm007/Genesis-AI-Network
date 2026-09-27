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



def test_dependency_graph_tracks_shared_blocker_multiple_parents():
    issues = [
        _issue(100),
        _issue(101, labels=("priority-high",)),
        _issue(200, body="<!-- genesis-capability-work:abc -->"),
    ]
    comments = {
        100: [{"body": "<!-- genesis-capability-dependency:200 -->"}],
        101: [{"body": "<!-- genesis-capability-dependency:200 -->"}],
        200: [],
    }

    graph = module.dependency_graph(issues, comments)

    assert graph["parents_by_capability"][200] == {100, 101}
    assert graph["dependencies_by_parent"] == {100: {200}, 101: {200}}
    assert graph["invalid_edges"] == []
    assert graph["cycles"] == []


def test_dependency_graph_rejects_missing_self_and_cyclic_dependencies():
    issues = [
        _issue(100),
        _issue(200, body="<!-- genesis-capability-work:a -->"),
        _issue(201, body="<!-- genesis-capability-work:b -->"),
    ]
    comments = {
        100: [
            {"body": "<!-- genesis-capability-dependency:999 -->"},
            {"body": "<!-- genesis-capability-dependency:100 -->"},
        ],
        200: [{"body": "<!-- genesis-capability-dependency:201 -->"}],
        201: [{"body": "<!-- genesis-capability-dependency:200 -->"}],
    }

    graph = module.dependency_graph(issues, comments)
    reasons = {(parent, capability, reason) for parent, capability, reason in graph["invalid_edges"]}

    assert (100, 999, "missing_capability") in reasons
    assert (100, 100, "self_cycle") in reasons
    assert (200, 201, "cycle") in reasons
    assert (201, 200, "cycle") in reasons
    assert 200 not in graph["dependencies_by_parent"]
    assert 201 not in graph["dependencies_by_parent"]


def test_score_includes_parent_priority_and_expected_reuse():
    issue = _issue(200, body="<!-- genesis-capability-work:abc -->")
    now = datetime(2026, 9, 25, tzinfo=timezone.utc)

    low = module.score_issue(
        issue,
        [],
        now=now,
        blocked_issues=1,
        parent_priority=0.25,
        expected_reuse=0.4,
    )
    high = module.score_issue(
        issue,
        [],
        now=now,
        blocked_issues=3,
        parent_priority=1.0,
        expected_reuse=0.95,
    )

    assert high["score"] > low["score"]
    assert high["parent_priority"] == 1.0
    assert high["expected_reuse"] == 0.95
