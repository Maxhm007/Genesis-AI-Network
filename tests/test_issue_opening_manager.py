from genesis.issue_opening_manager import annotate_body, decide


def _issue(number: int, title: str, body: str, *, state: str = "OPEN") -> dict:
    return {
        "number": number,
        "title": title,
        "body": body,
        "state": state,
        "url": f"https://example.test/issues/{number}",
        "createdAt": "2026-09-21T00:00:00Z",
        "closedAt": None,
    }


def test_annotation_records_opening_lane_once():
    body = annotate_body("hello", "deepseek-selfdev-discovery")
    assert "Genesis-Opening-Lane: deepseek-selfdev-discovery" in body
    assert body.count("genesis-issue-opening-manager") == 1
    assert annotate_body(body, "deepseek-selfdev-discovery").count("genesis-issue-opening-manager") == 1


def test_cross_lane_duplicate_is_suppressed_by_target_and_similarity():
    existing = _issue(
        10,
        "[Genesis Task] new capability — persistent memory",
        "Genesis-Opening-Lane: recent-ai-capability-discovery\n- **Target:** `genesis/learned_capabilities.py`\nAdd persistent agent memory with provenance.",
    )
    decision = decide(
        lane="missing-qwen-capability-discovery",
        title="[Genesis Task] new capability — missing baseline: Persistent agent memory",
        body="- **Target:** `genesis/learned_capabilities.py`\nAdd persistent agent memory with provenance and lifecycle controls.",
        issues=[existing],
        severity="medium",
        value_score=70,
    )
    assert decision.action == "duplicate"
    assert decision.duplicate_issue_number == 10


def test_critical_lane_bypasses_backlog_pressure():
    issues = [
        _issue(i, f"Open issue {i}", f"body {i}")
        for i in range(1, 60)
    ]
    decision = decide(
        lane="action-failure-watcher",
        title="Genesis Action failure: workflow / test",
        body="unique critical failure",
        issues=issues,
        severity="critical",
        value_score=100,
        bypass_backlog=True,
    )
    assert decision.action == "publish"


def test_low_value_discovery_defers_when_backlog_is_overloaded():
    issues = [
        _issue(i, f"Open issue {i}", f"body {i}")
        for i in range(1, 60)
    ]
    decision = decide(
        lane="gene-peer-issue-sync",
        title="Peer improvement",
        body="unique peer improvement",
        issues=issues,
        severity="medium",
        value_score=40,
    )
    assert decision.action == "defer"
