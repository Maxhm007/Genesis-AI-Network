from pathlib import Path

from genesis.human_oversight import HumanOversight


def test_owner_goal_becomes_traceable_agentic_issue_candidate(tmp_path: Path) -> None:
    oversight = HumanOversight(tmp_path)
    goal = oversight.define_goal(
        title="Improve autonomous issue closure",
        objective="Reduce unresolved actionable issues while preserving validation safeguards.",
        priority=90,
        success_criteria=["Closure Manager verifies and seals completed work"],
        protected_boundaries=["Do not weaken validation or security"],
    )

    candidate = oversight.issue_candidate(goal["goal_id"])

    assert candidate["lane"] == "owner-goal"
    assert candidate["bypass_backlog"] is True
    assert "Genesis-Owner-Goal:" in candidate["body"]
    assert "Do not weaken validation or security" in candidate["body"]


def test_priority_change_preserves_provenance(tmp_path: Path) -> None:
    oversight = HumanOversight(tmp_path)
    goal = oversight.define_goal(title="Goal", objective="Do something useful", priority=40)

    updated = oversight.change_priority(goal["goal_id"], 85, reason="Owner raised urgency")

    assert updated["priority"] == 85
    assert updated["priority_history"][-1]["from"] == 40
    assert updated["priority_history"][-1]["to"] == 85
    assert updated["priority_history"][-1]["reason"] == "Owner raised urgency"


def test_ordinary_in_boundary_operation_does_not_escalate(tmp_path: Path) -> None:
    oversight = HumanOversight(tmp_path)
    goal = oversight.define_goal(title="Goal", objective="Routine autonomous work")

    escalated = oversight.escalate(
        goal["goal_id"],
        reason="ordinary implementation choice",
        requires_owner_authority=False,
        ambiguity=False,
    )

    assert escalated is False
    assert oversight.report(goal["goal_id"])["human_decisions_required"] == []


def test_true_owner_authority_decision_is_surfaced(tmp_path: Path) -> None:
    oversight = HumanOversight(tmp_path)
    goal = oversight.define_goal(title="Goal", objective="Governed work")

    assert oversight.escalate(
        goal["goal_id"],
        reason="Changing protected boundary requires owner authority",
        requires_owner_authority=True,
    )

    report = oversight.report(goal["goal_id"])
    assert len(report["human_decisions_required"]) == 1
    assert report["human_decisions_required"][0]["requires_owner_authority"] is True


def test_evidence_first_completion_reporting_and_metrics(tmp_path: Path) -> None:
    oversight = HumanOversight(tmp_path)
    goal = oversight.define_goal(title="Goal", objective="Complete verified work")
    oversight.attach_issue(goal["goal_id"], 123)
    oversight.record_evidence(
        goal["goal_id"],
        kind="test",
        reference="run:42",
        status="success",
        summary="Focused and full validation passed",
    )
    oversight.record_evidence(
        goal["goal_id"],
        kind="issue",
        reference="#123",
        status="complete",
        summary="Authoritative issue closed and sealed",
    )

    assert oversight.complete_if_verified(goal["goal_id"]) is True
    report = oversight.report(
        goal["goal_id"],
        metrics={"closure_velocity": 4, "health": "healthy"},
    )

    assert report["status"] == "complete"
    assert report["traceability"]["issues"] == [123]
    assert report["evidence_summary"] == {"total": 2, "validated": 2}
    assert report["metrics"]["closure_velocity"] == 4
