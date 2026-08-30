from pathlib import Path

from genesis.pulse import adaptive_recovery_interval, recovery_pulse_due


SOLVER = Path(".github/workflows/genesis-oldest-issue-solver.yml")
WORKER = Path(".github/workflows/genesis-bounded-repair-worker.yml")


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


def test_current_solver_runs_five_minute_safety_net_and_self_chains() -> None:
    text = SOLVER.read_text(encoding="utf-8")
    assert "interval=300" in text
    assert "max_cycles=64" in text
    assert "Start successor solver run" in text
    assert "genesis-oldest-issue-solver.yml/dispatches" in text


def test_current_repair_capacity_is_single_issue_lane() -> None:
    solver = SOLVER.read_text(encoding="utf-8")
    worker = WORKER.read_text(encoding="utf-8")
    assert "group: genesis-oldest-real-issue-solver" in solver
    assert "cancel-in-progress: true" in solver
    assert "genesis-repair-in-progress" in solver
    assert "group: genesis-bounded-repair-${{ inputs.issue_number }}" in worker
