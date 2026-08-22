from pathlib import Path

from genesis.pulse import GenePulse, workflow_chain_decision


def test_focused_issue_requests_immediate_continuation(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        "genesis.pulse.run_step",
        lambda logical_id: {
            "decision": {"mode": "solve_issue", "task_id": "task-1"},
            "action": "attempt_focused_issue",
        },
    )
    result = GenePulse(tmp_path, "gene-node-2").run()
    assert result.logical_id == "gene-node-2"
    assert result.task_id == "task-1"
    assert result.needs_next_pulse is True
    assert result.next_pulse_reason == "focused_issue_has_executable_work"


def test_owner_stop_ends_pulse_chain(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        "genesis.pulse.run_step",
        lambda logical_id: {
            "decision": {"mode": "stopped", "task_id": None},
            "action": "owner_stop",
        },
    )
    result = GenePulse(tmp_path).run()
    assert result.needs_next_pulse is False
    assert result.next_pulse_reason == "owner_stop"


def test_idle_discovery_checkpoints_instead_of_spinning(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        "genesis.pulse.run_step",
        lambda logical_id: {
            "decision": {"mode": "learn_discover", "task_id": None},
            "action": "learn_discover_reassess",
            "next_decision": {"mode": "learn_discover", "task_id": None},
        },
    )
    result = GenePulse(tmp_path).run()
    assert result.mode == "learn_discover"
    assert result.needs_next_pulse is False
    assert result.next_pulse_reason == "idle_discovery_checkpointed"


def test_discovery_chains_when_it_creates_executable_work(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        "genesis.pulse.run_step",
        lambda logical_id: {
            "decision": {"mode": "learn_discover", "task_id": None},
            "action": "learn_discover_reassess",
            "next_decision": {"mode": "solve_issue", "task_id": "task-2"},
        },
    )
    result = GenePulse(tmp_path).run()
    assert result.needs_next_pulse is True
    assert result.next_pulse_reason == "discovery_created_executable_issue"


def test_promotion_observed_continues_to_next_discovery(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        "genesis.pulse.run_step",
        lambda logical_id: {
            "decision": {"mode": "solve_issue", "task_id": "task-4"},
            "action": "promotion_observed_reassess",
            "next_decision": {"mode": "learn_discover", "task_id": None},
        },
    )
    result = GenePulse(tmp_path).run()
    assert result.needs_next_pulse is True
    assert result.next_pulse_reason == "validated_promotion_observed_continue_discovery"


def test_validation_wait_checkpoints_until_external_event(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        "genesis.pulse.run_step",
        lambda logical_id: {
            "decision": {"mode": "solve_issue", "task_id": "task-3"},
            "action": "hold_focus_while_validation_finishes",
        },
    )
    result = GenePulse(tmp_path).run()
    assert result.needs_next_pulse is False
    assert result.next_pulse_reason == "waiting_for_independent_validation"


def test_unknown_action_fails_closed(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        "genesis.pulse.run_step",
        lambda logical_id: {
            "decision": {"mode": "future_mode", "task_id": None},
            "action": "future_unrecognized_action",
        },
    )
    result = GenePulse(tmp_path).run()
    assert result.needs_next_pulse is False
    assert result.next_pulse_reason == "unrecognized_action_checkpointed"


def test_idle_checkpoint_gets_bounded_extra_discovery_pulse() -> None:
    dispatch, next_budget, reason = workflow_chain_decision(
        needs_next_pulse=False,
        next_pulse_reason="idle_discovery_checkpointed",
        idle_budget=4,
    )
    assert dispatch is True
    assert next_budget == 3
    assert reason == "bounded_idle_discovery_burst"


def test_idle_discovery_burst_stops_when_budget_is_exhausted() -> None:
    dispatch, next_budget, reason = workflow_chain_decision(
        needs_next_pulse=False,
        next_pulse_reason="idle_discovery_checkpointed",
        idle_budget=1,
    )
    assert dispatch is False
    assert next_budget == 0
    assert reason == "idle_discovery_budget_exhausted"


def test_executable_work_resets_idle_discovery_budget() -> None:
    dispatch, next_budget, reason = workflow_chain_decision(
        needs_next_pulse=True,
        next_pulse_reason="candidate_waiting_internal_review",
        idle_budget=2,
    )
    assert dispatch is True
    assert next_budget == 4
    assert reason == "executable_work_continues"


def test_validation_checkpoint_does_not_use_idle_discovery_budget() -> None:
    dispatch, next_budget, reason = workflow_chain_decision(
        needs_next_pulse=False,
        next_pulse_reason="waiting_for_independent_validation",
        idle_budget=4,
    )
    assert dispatch is False
    assert next_budget == 4
    assert reason == "checkpoint_preserved"
