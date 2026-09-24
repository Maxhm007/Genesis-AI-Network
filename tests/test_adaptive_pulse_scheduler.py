from pathlib import Path

from genesis.pulse import adaptive_recovery_interval, recovery_pulse_due


AGENTIC = Path(".github/workflows/genesis-agentic-lab-recovery.yml")
WORKER = Path(".github/workflows/genesis-bounded-repair-worker.yml")
WAKEUP = Path(".github/workflows/genesis-repair-worker-successor-wakeup.yml")


def test_adaptive_recovery_interval_accelerates_under_high_backlog() -> None:
    decision = adaptive_recovery_interval(backlog_count=62, action_failure_count=0)
    assert decision.interval_minutes == 5
    assert decision.reason == "high_repository_pressure"


def test_adaptive_recovery_interval_uses_normal_active_cadence() -> None:
    decision = adaptive_recovery_interval(backlog_count=4, action_failure_count=0)
    assert decision.interval_minutes == 10


def test_adaptive_recovery_interval_slows_when_idle() -> None:
    decision = adaptive_recovery_interval(backlog_count=0, action_failure_count=0)
    assert decision.interval_minutes == 30


def test_recovery_pulse_due_uses_selected_interval() -> None:
    assert recovery_pulse_due(last_completed_age_seconds=None, interval_minutes=30) is True
    assert recovery_pulse_due(last_completed_age_seconds=599, interval_minutes=10) is False
    assert recovery_pulse_due(last_completed_age_seconds=600, interval_minutes=10) is True


def test_agentic_lab_is_authoritative_recovery_scheduler() -> None:
    text = AGENTIC.read_text(encoding="utf-8")
    assert "schedule:" in text
    assert "agentic_parallel_dispatch.py" in text
    assert "issues: write" in text
    assert "actions: write" in text


def test_worker_completion_returns_control_to_agentic_lab() -> None:
    text = WAKEUP.read_text(encoding="utf-8")
    assert "workflow_run:" in text
    assert "Genesis Bounded Repair Worker" in text
    assert "Genesis Agentic Strategy Worker" in text
    assert "gh workflow run genesis-agentic-lab-recovery.yml" in text
    assert "genesis-sequential-issue-controller.yml" not in text


def test_bounded_worker_returns_control_to_agentic_lab() -> None:
    text = WORKER.read_text(encoding="utf-8")
    assert "actions: write" in text
    assert "Return control to Agentic Lab" in text
    assert "gh workflow run genesis-agentic-lab-recovery.yml" in text
    assert "genesis-sequential-issue-controller.yml" not in text
