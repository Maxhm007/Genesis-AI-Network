from __future__ import annotations

import genesis.pulse as pulse_module
from genesis.pulse import GenePulse


def _backlog() -> dict:
    return {
        "status": "ok",
        "open_issue_count": 2,
        "created_count": 0,
        "issues": [
            {"issue": 801, "kind": "development", "managed": True},
            {"issue": 802, "kind": "issue_autorepair_specialist", "managed": True},
        ],
    }


def test_gene_pulse_reconciles_authority_before_bounded_execution(tmp_path, monkeypatch) -> None:
    events: list[object] = []
    monkeypatch.setattr(pulse_module, "issue_authority_enabled", lambda root: True)
    monkeypatch.setattr(
        pulse_module,
        "reconcile_terminal_github_issues",
        lambda root: events.append("terminal") or {"status": "ok", "blocked": []},
    )
    monkeypatch.setattr(
        pulse_module,
        "ingest_open_issue_backlog",
        lambda root: events.append("intake") or _backlog(),
    )

    def closed_sync(root, *, open_issue_numbers):
        events.append(("closed_sync", set(open_issue_numbers)))
        return {"status": "ok", "blocked": []}

    monkeypatch.setattr(pulse_module, "reconcile_closed_github_issue_tasks", closed_sync)
    monkeypatch.setattr(
        pulse_module,
        "route_unbacked_tasks",
        lambda root: events.append("route") or {"status": "ok", "blocked": []},
    )
    monkeypatch.setattr(
        pulse_module,
        "run_step",
        lambda logical_id: events.append("run_step")
        or {"decision": {"mode": "idle", "task_id": None}, "action": "focus_missing_reassess"},
    )

    result = GenePulse(tmp_path).run()

    assert events[:5] == [
        "terminal",
        "intake",
        ("closed_sync", {801, 802}),
        "route",
        "run_step",
    ]
    assert result.payload["github_terminal_reconcile_before"]["status"] == "ok"
    assert result.payload["github_closed_issue_sync"]["status"] == "ok"


def test_gene_pulse_fails_closed_when_closed_issue_authority_sync_is_blocked(tmp_path, monkeypatch) -> None:
    executed = {"run_step": False}
    monkeypatch.setattr(pulse_module, "issue_authority_enabled", lambda root: True)
    monkeypatch.setattr(
        pulse_module,
        "reconcile_terminal_github_issues",
        lambda root: {"status": "ok", "blocked": []},
    )
    monkeypatch.setattr(pulse_module, "ingest_open_issue_backlog", lambda root: _backlog())
    monkeypatch.setattr(
        pulse_module,
        "reconcile_closed_github_issue_tasks",
        lambda root, *, open_issue_numbers: {
            "status": "blocked",
            "blocked": [{"github_issue_number": 999, "reason": "github unavailable"}],
        },
    )
    monkeypatch.setattr(pulse_module, "route_unbacked_tasks", lambda root: {"status": "ok", "blocked": []})

    def run_step(logical_id):
        executed["run_step"] = True
        return {"decision": {"mode": "should_not_run"}, "action": "unexpected"}

    monkeypatch.setattr(pulse_module, "run_step", run_step)

    result = GenePulse(tmp_path).run()

    assert result.action == "github_issue_sync_blocked"
    assert result.next_pulse_reason == "github_issue_authority_unavailable"
    assert executed["run_step"] is False


def test_gene_pulse_fails_closed_when_terminal_reconcile_is_blocked(tmp_path, monkeypatch) -> None:
    called = {"intake": False}
    monkeypatch.setattr(pulse_module, "issue_authority_enabled", lambda root: True)
    monkeypatch.setattr(
        pulse_module,
        "reconcile_terminal_github_issues",
        lambda root: {"status": "blocked", "blocked": [{"reason": "cannot verify linked issue"}]},
    )

    def intake(root):
        called["intake"] = True
        return _backlog()

    monkeypatch.setattr(pulse_module, "ingest_open_issue_backlog", intake)

    result = GenePulse(tmp_path).run()

    assert result.action == "github_issue_sync_blocked"
    assert called["intake"] is False
