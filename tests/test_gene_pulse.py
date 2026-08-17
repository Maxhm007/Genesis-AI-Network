from pathlib import Path

from genesis.pulse import GenePulse


def test_pulse_requests_continuation(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr("genesis.pulse.run_step", lambda logical_id: {
        "decision": {"mode": "solve_issue", "task_id": "task-1"},
        "action": "attempt_focused_issue",
    })
    result = GenePulse(tmp_path, "gene-node-2").run()
    assert result.logical_id == "gene-node-2"
    assert result.task_id == "task-1"
    assert result.needs_next_pulse is True


def test_owner_stop_ends_pulse_chain(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr("genesis.pulse.run_step", lambda logical_id: {
        "decision": {"mode": "stopped", "task_id": None},
        "action": "owner_stop",
    })
    result = GenePulse(tmp_path).run()
    assert result.needs_next_pulse is False


def test_discovery_also_requests_next_pulse(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr("genesis.pulse.run_step", lambda logical_id: {
        "decision": {"mode": "learn_discover", "task_id": None},
        "action": "learn_discover_reassess",
    })
    result = GenePulse(tmp_path).run()
    assert result.mode == "learn_discover"
    assert result.needs_next_pulse is True
