from datetime import datetime, timedelta, timezone

import scripts.issue_lifecycle_health_watchdog as module


NOW = datetime(2026, 9, 26, 6, 0, tzinfo=timezone.utc)


def _run(name: str, *, minutes_ago: int = 5, conclusion: str = "success") -> dict:
    return {
        "id": 100,
        "name": name,
        "status": "completed",
        "conclusion": conclusion,
        "updated_at": (NOW - timedelta(minutes=minutes_ago)).isoformat(),
    }


def _issue(number: int, *, state: str = "open", labels=(), minutes_ago: int = 5) -> dict:
    return {
        "number": number,
        "state": state,
        "updated_at": (NOW - timedelta(minutes=minutes_ago)).isoformat(),
        "labels": [{"name": label} for label in labels],
    }


def test_healthy_when_both_managers_are_current_and_no_verified_issue_is_stuck():
    result = module.evaluate(
        opening_run=_run(module.OPENING_WORKFLOW, minutes_ago=20),
        closure_run=_run(module.CLOSURE_WORKFLOW, minutes_ago=5),
        issues=[_issue(10, labels=("genesis-autonomous",))],
        now=NOW,
        opening_max_age_minutes=75,
        closure_max_age_minutes=30,
        verified_open_grace_minutes=20,
    )
    assert result["healthy"] is True
    assert result["faults"] == []


def test_detects_stale_or_failed_managers():
    result = module.evaluate(
        opening_run=_run(module.OPENING_WORKFLOW, minutes_ago=90),
        closure_run=_run(module.CLOSURE_WORKFLOW, minutes_ago=5, conclusion="failure"),
        issues=[],
        now=NOW,
        opening_max_age_minutes=75,
        closure_max_age_minutes=30,
        verified_open_grace_minutes=20,
    )
    assert result["healthy"] is False
    assert any(fault.startswith("opening_manager_stale:") for fault in result["faults"])
    assert "closing_manager_latest_run_failure" in result["faults"]


def test_detects_verified_issue_that_closure_manager_failed_to_close():
    result = module.evaluate(
        opening_run=_run(module.OPENING_WORKFLOW),
        closure_run=_run(module.CLOSURE_WORKFLOW),
        issues=[_issue(857, labels=("genesis-verified",), minutes_ago=45)],
        now=NOW,
        opening_max_age_minutes=75,
        closure_max_age_minutes=30,
        verified_open_grace_minutes=20,
    )
    assert result["healthy"] is False
    assert "verified_issues_not_auto_closed:857" in result["faults"]


def test_recent_verified_issue_gets_grace_period():
    result = module.evaluate(
        opening_run=_run(module.OPENING_WORKFLOW),
        closure_run=_run(module.CLOSURE_WORKFLOW),
        issues=[_issue(857, labels=("genesis-verified",), minutes_ago=8)],
        now=NOW,
        opening_max_age_minutes=75,
        closure_max_age_minutes=30,
        verified_open_grace_minutes=20,
    )
    assert result["healthy"] is True


def test_heal_actions_dispatches_stale_opening_and_closing_managers(monkeypatch):
    calls: list[str] = []
    monkeypatch.setattr(
        module,
        "_dispatch_workflow",
        lambda repository, workflow: calls.append(workflow) or True,
    )
    assessment = {
        "faults": [
            "opening_manager_stale:90.0m>75m",
            "closing_manager_stale:45.0m>30m",
            "verified_issues_not_auto_closed:857",
        ],
        "evidence": {},
    }

    result = module._heal_actions(assessment, "owner/repo")

    assert result["failed"] == []
    assert result["dispatched"] == [
        "genesis-issue-opening-manager.yml",
        "genesis-issue-closure-manager.yml",
    ]
    assert calls == result["dispatched"]


def test_persistent_fault_requires_more_than_one_stale_window():
    transient = {
        "faults": ["closing_manager_stale:35.0m>30m"],
        "evidence": {"closing_run": {"age_minutes": 35.0}},
    }
    persistent = {
        "faults": ["closing_manager_stale:75.0m>30m"],
        "evidence": {"closing_run": {"age_minutes": 75.0}},
    }

    assert module._persistent_fault(
        transient,
        opening_max_age_minutes=75,
        closure_max_age_minutes=30,
        verified_open_grace_minutes=20,
    ) is False
    assert module._persistent_fault(
        persistent,
        opening_max_age_minutes=75,
        closure_max_age_minutes=30,
        verified_open_grace_minutes=20,
    ) is True
