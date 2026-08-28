from pathlib import Path

from genesis.pulse import adaptive_recovery_interval, recovery_pulse_due


AUTOREPAIR = Path(".github/workflows/github-issue-autorepair.yml")


def test_adaptive_recovery_interval_accelerates_under_high_backlog() -> None:
    decision = adaptive_recovery_interval(backlog_count=62, action_failure_count=0)
    assert decision.interval_minutes == 5
    assert decision.reason == "high_repository_pressure"


def test_adaptive_recovery_interval_uses_normal_active_cadence() -> None:
    decision = adaptive_recovery_interval(backlog_count=4, action_failure_count=0)
    assert decision.interval_minutes == 10
    assert decision.reason == "active_repository_pressure"


def test_adaptive_recovery_interval_slows_when_idle() -> None:
    decision = adaptive_recovery_interval(backlog_count=0, action_failure_count=0)
    assert decision.interval_minutes == 30
    assert decision.reason == "idle_repository"


def test_action_failures_accelerate_recovery_even_with_small_backlog() -> None:
    decision = adaptive_recovery_interval(backlog_count=1, action_failure_count=3)
    assert decision.interval_minutes == 5


def test_recovery_pulse_due_uses_selected_interval() -> None:
    assert recovery_pulse_due(last_completed_age_seconds=None, interval_minutes=30) is True
    assert recovery_pulse_due(last_completed_age_seconds=599, interval_minutes=10) is False
    assert recovery_pulse_due(last_completed_age_seconds=600, interval_minutes=10) is True


def test_autorepair_admission_is_event_driven_for_open_reopen_and_authorized_labels() -> None:
    text = AUTOREPAIR.read_text(encoding="utf-8")
    assert "types: [opened, reopened, labeled]" in text
    assert "github.event_name != 'issues' ||" in text
    assert "github.event.action != 'labeled' ||" in text
    assert "github.event.label.name == 'genesis-autonomous'" in text
    assert "github.event.label.name == 'genesis-task'" in text


def test_autorepair_preserves_immediate_refill_and_single_lane_capacity() -> None:
    text = AUTOREPAIR.read_text(encoding="utf-8")
    assert "GENESIS_ISSUE_REPAIR_MAX_PARALLEL: '1'" in text
    assert "refill:" in text
    assert "gh workflow run github-issue-autorepair-heartbeat.yml" in text
    assert "github-issue-autorepair-integration.yml" in text
