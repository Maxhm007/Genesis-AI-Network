from datetime import datetime, timedelta, timezone

import scripts.nexus_autonomy_watchdog as module

NOW = datetime(2026, 10, 1, 14, 0, tzinfo=timezone.utc)


def _run(name: str, minutes_ago: int = 5, conclusion: str = "success") -> dict:
    return {
        "id": 1,
        "name": name,
        "status": "completed",
        "conclusion": conclusion,
        "updated_at": (NOW - timedelta(minutes=minutes_ago)).isoformat(),
    }


def _issue(number: int, labels=(), minutes_ago: int = 5) -> dict:
    return {
        "number": number,
        "state": "open",
        "labels": [{"name": label} for label in labels],
        "updated_at": (NOW - timedelta(minutes=minutes_ago)).isoformat(),
    }


def test_healthy_when_heartbeats_are_current_and_work_is_active():
    result = module.evaluate(
        team_run=_run(module.TEAM_WORKFLOW),
        agentic_run=_run(module.AGENTIC_WORKFLOW),
        issues=[
            _issue(10, labels=("genesis-autonomous", "genesis-working")),
        ],
        now=NOW,
    )
    assert result["healthy"] is True
    assert result["faults"] == []


def test_detects_stale_team_or_agentic_heartbeat():
    result = module.evaluate(
        team_run=_run(module.TEAM_WORKFLOW, minutes_ago=50),
        agentic_run=_run(module.AGENTIC_WORKFLOW, minutes_ago=30),
        issues=[],
        now=NOW,
    )
    assert result["healthy"] is False
    assert any(x.startswith("team_heartbeat_stale:") for x in result["faults"])
    assert any(x.startswith("agentic_lab_heartbeat_stale:") for x in result["faults"])


def test_detects_backlog_without_active_worker():
    result = module.evaluate(
        team_run=_run(module.TEAM_WORKFLOW),
        agentic_run=_run(module.AGENTIC_WORKFLOW),
        issues=[_issue(20, labels=("genesis-autonomous",))],
        now=NOW,
    )
    assert result["healthy"] is False
    assert "actionable_backlog_has_no_active_autonomous_worker" in result["faults"]


def test_detects_stalled_autonomous_issue():
    result = module.evaluate(
        team_run=_run(module.TEAM_WORKFLOW),
        agentic_run=_run(module.AGENTIC_WORKFLOW),
        issues=[_issue(30, labels=("genesis-autonomous",), minutes_ago=120)],
        now=NOW,
    )
    assert result["healthy"] is False
    assert "stalled_autonomous_issues:30" in result["faults"]


def test_ignores_verified_or_non_actionable_issues():
    result = module.evaluate(
        team_run=_run(module.TEAM_WORKFLOW),
        agentic_run=_run(module.AGENTIC_WORKFLOW),
        issues=[
            _issue(40, labels=("genesis-autonomous", "genesis-verified"), minutes_ago=200),
            _issue(41, labels=("genesis-autonomous", "genesis-persistent"), minutes_ago=200),
        ],
        now=NOW,
    )
    assert result["healthy"] is True
