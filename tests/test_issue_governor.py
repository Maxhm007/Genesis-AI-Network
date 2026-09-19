from __future__ import annotations

from datetime import datetime, timedelta, timezone

from genesis.issue_governor import (
    OCCURRENCE_MARKER,
    PROBLEM_MARKER,
    backlog_health,
    equivalent_issue,
    issue_value_score,
    occurrence_fingerprint,
    problem_fingerprint,
    publication_decision,
)


def test_active_equivalent_problem_is_reused_even_when_occurrence_changes():
    problem = problem_fingerprint(
        target="genesis/a.py",
        failure_class="repository_discovery",
        objective="reject invalid values",
    )
    old_occurrence = occurrence_fingerprint(
        target="genesis/a.py",
        failure_class="repository_discovery",
        objective="reject invalid values",
        evidence="OLD = bad",
        source_revision="1111",
    )
    new_occurrence = occurrence_fingerprint(
        target="genesis/a.py",
        failure_class="repository_discovery",
        objective="reject invalid values",
        evidence="NEW = bad",
        source_revision="2222",
    )
    issues = [{
        "number": 10,
        "state": "OPEN",
        "body": f"{PROBLEM_MARKER} {problem}\n{OCCURRENCE_MARKER} {old_occurrence}\n",
    }]

    relation, issue = equivalent_issue(
        issues,
        problem_fp=problem,
        occurrence_fp=new_occurrence,
    )

    assert relation == "reuse_open"
    assert issue["number"] == 10


def test_closed_problem_allows_fresh_regression_but_blocks_same_occurrence():
    problem = problem_fingerprint(
        target="genesis/a.py",
        failure_class="repository_discovery",
        objective="reject invalid values",
    )
    old_occurrence = occurrence_fingerprint(
        target="genesis/a.py",
        failure_class="repository_discovery",
        objective="reject invalid values",
        evidence="OLD = bad",
        source_revision="1111",
    )
    fresh_occurrence = occurrence_fingerprint(
        target="genesis/a.py",
        failure_class="repository_discovery",
        objective="reject invalid values",
        evidence="NEW = bad",
        source_revision="2222",
    )
    issues = [{
        "number": 10,
        "state": "CLOSED",
        "body": f"{PROBLEM_MARKER} {problem}\n{OCCURRENCE_MARKER} {old_occurrence}\n",
    }]

    relation, issue = equivalent_issue(issues, problem_fp=problem, occurrence_fp=fresh_occurrence)
    assert relation == "new"
    assert issue is None

    relation, issue = equivalent_issue(issues, problem_fp=problem, occurrence_fp=old_occurrence)
    assert relation == "reuse_closed_occurrence"
    assert issue["number"] == 10


def test_backlog_governor_defers_lower_value_work_but_critical_bypasses():
    overloaded = backlog_health(
        open_count=80,
        opened_24h=12,
        closed_24h=3,
        healthy_limit=25,
        warning_limit=50,
    )
    assert overloaded.state == "overloaded"
    assert publication_decision(
        health=overloaded,
        value_score=52,
        severity="medium",
    ) == "defer"
    assert publication_decision(
        health=overloaded,
        value_score=20,
        severity="critical",
    ) == "publish"


def test_backlog_recovery_releases_same_candidate_without_changing_value():
    overloaded = backlog_health(open_count=70, opened_24h=8, closed_24h=2)
    healthy = backlog_health(open_count=12, opened_24h=1, closed_24h=6)
    score = issue_value_score(
        severity="medium",
        blocked_issues=1,
        age_hours=12,
        reuse_value=0.5,
        owner_priority=0,
        retry_depth=0,
        success_probability=0.8,
    ).score

    assert publication_decision(health=overloaded, value_score=score, severity="medium") == "defer"
    assert publication_decision(health=healthy, value_score=score, severity="medium") == "publish"


def test_age_bonus_prevents_permanent_starvation():
    fresh = issue_value_score(
        severity="medium",
        blocked_issues=0,
        age_hours=0,
        reuse_value=0.5,
        owner_priority=0,
        retry_depth=0,
        success_probability=0.7,
    )
    old = issue_value_score(
        severity="medium",
        blocked_issues=0,
        age_hours=24 * 30,
        reuse_value=0.5,
        owner_priority=0,
        retry_depth=0,
        success_probability=0.7,
    )

    assert old.score > fresh.score
    assert old.breakdown["age"] == 18.0


def test_value_score_is_deterministic_and_explainable():
    first = issue_value_score(
        severity="high",
        blocked_issues=4,
        age_hours=72,
        reuse_value=0.8,
        owner_priority=1.0,
        retry_depth=2,
        success_probability=0.75,
    )
    second = issue_value_score(
        severity="high",
        blocked_issues=4,
        age_hours=72,
        reuse_value=0.8,
        owner_priority=1.0,
        retry_depth=2,
        success_probability=0.75,
    )

    assert first == second
    assert set(first.breakdown) == {
        "severity",
        "blocked_issues",
        "age",
        "reuse_value",
        "owner_priority",
        "success_probability",
        "retry_penalty",
    }


def test_equivalent_issue_resolves_open_successor_to_root():
    problem = "genesis-problem:abc"
    occurrence = "genesis-occurrence:one"
    root = {
        "number": 10,
        "state": "open",
        "labels": [{"name": "genesis-task"}],
        "body": f"{PROBLEM_MARKER} {problem}\n{OCCURRENCE_MARKER} {occurrence}",
    }
    successor = {
        "number": 11,
        "state": "open",
        "labels": [{"name": "genesis-task"}],
        "body": (
            "<!-- genesis-unsolved-root:10 -->\n"
            "<!-- genesis-unsolved-successor-of:10 -->\n"
            f"{PROBLEM_MARKER} {problem}\n"
            f"{OCCURRENCE_MARKER} {occurrence}"
        ),
    }

    relation, issue = equivalent_issue(
        [successor, root],
        problem_fp=problem,
        occurrence_fp=occurrence,
    )

    assert relation == "reuse_open_root"
    assert issue["number"] == 10


def test_stale_successor_of_verified_root_does_not_suppress_fresh_recurrence():
    problem = "genesis-problem:abc"
    old_occurrence = "genesis-occurrence:old"
    fresh_occurrence = "genesis-occurrence:fresh"
    root = {
        "number": 20,
        "state": "closed",
        "state_reason": "completed",
        "labels": [{"name": "genesis-task"}, {"name": "genesis-verified"}],
        "body": f"{PROBLEM_MARKER} {problem}\n{OCCURRENCE_MARKER} {old_occurrence}",
    }
    stale_successor = {
        "number": 21,
        "state": "open",
        "labels": [{"name": "genesis-task"}],
        "body": (
            "<!-- genesis-unsolved-root:20 -->\n"
            f"{PROBLEM_MARKER} {problem}\n"
            f"{OCCURRENCE_MARKER} {old_occurrence}"
        ),
    }

    relation, issue = equivalent_issue(
        [stale_successor, root],
        problem_fp=problem,
        occurrence_fp=fresh_occurrence,
    )

    assert relation == "new"
    assert issue is None
