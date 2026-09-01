from pathlib import Path

from genesis.pulse import adaptive_recovery_interval, recovery_pulse_due


CONTROLLER = Path(".github/workflows/genesis-sequential-issue-controller.yml")
WORKER = Path(".github/workflows/genesis-bounded-repair-worker.yml")
WAKEUP = Path(".github/workflows/genesis-repair-worker-successor-wakeup.yml")


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


def test_current_controller_has_independent_ten_minute_safety_net() -> None:
    text = CONTROLLER.read_text(encoding="utf-8")
    assert "schedule:" in text
    assert "cron: '*/10 * * * *'" in text
    assert "group: genesis-sequential-issue-controller" in text
    assert "Start successor solver run" not in text
    assert "genesis-oldest-issue-solver.yml/dispatches" not in text


def test_worker_completion_wakes_authoritative_controller_without_self_respawn() -> None:
    text = WAKEUP.read_text(encoding="utf-8")
    assert "workflow_run:" in text
    assert "Genesis Bounded Repair Worker" in text
    assert "completed" in text
    assert "gh workflow run genesis-sequential-issue-controller.yml" in text
    assert "--ref main" in text
    assert "genesis-bounded-repair-worker.yml" not in text
    assert "Start successor solver run" not in text


def test_wakeup_merge_triggers_one_immediate_controller_probe() -> None:
    text = WAKEUP.read_text(encoding="utf-8")
    assert "push:" in text
    assert "branches: [main]" in text
    assert ".github/workflows/genesis-repair-worker-successor-wakeup.yml" in text
    assert "group: genesis-repair-worker-successor-wakeup" in text
    assert "cancel-in-progress: true" in text


def test_current_repair_capacity_is_single_issue_lane() -> None:
    controller = CONTROLLER.read_text(encoding="utf-8")
    worker = WORKER.read_text(encoding="utf-8")
    assert "active_count=" in controller
    assert "strict sequential mode will not start another issue" in controller
    assert "genesis-repair-in-progress" in controller
    assert "genesis-validating" in controller
    assert "group: genesis-bounded-repair-${{ inputs.issue_number }}" in worker
