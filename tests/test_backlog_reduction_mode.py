from __future__ import annotations

import os
from pathlib import Path

from genesis.issue_backpressure import BACKLOG_REDUCTION_MODE_ENV, configured_max_active
from genesis.issue_worker_pool import select_issue_repair_batch
from scripts import task_router


def _issue(number: int, title: str, updated: str) -> dict:
    return {
        "number": number,
        "state": "OPEN",
        "title": title,
        "updatedAt": updated,
        "labels": [{"name": "genesis-task"}],
    }


def test_backlog_reduction_mode_sets_capacity_limited_admission_to_zero() -> None:
    assert configured_max_active({BACKLOG_REDUCTION_MODE_ENV: "1"}) == 0
    # Existing explicit zero behavior remains unchanged outside drain mode.
    assert configured_max_active({"GENESIS_MAX_ACTIVE_AUTONOMOUS_ISSUES": "0"}) == 20


def test_task_router_defers_new_publishers_but_drains_existing_self_improvement(tmp_path: Path, monkeypatch) -> None:
    calls: list[str] = []

    def forbidden_capability(_root: Path) -> dict:
        raise AssertionError("capability issue publisher must not run during backlog reduction")

    def forbidden_self_improvement(_root: Path) -> dict:
        raise AssertionError("self-improvement issue publisher must not run during backlog reduction")

    def drain_existing(_root: Path) -> dict:
        calls.append("drain")
        assert os.environ.get(BACKLOG_REDUCTION_MODE_ENV) == "1"
        return {"status": "drain_existing_only", "routed": [], "deferred": []}

    def dedupe(_root: Path) -> dict:
        calls.append("dedupe")
        return {"status": "ok"}

    def general_router(_root: Path) -> dict:
        calls.append("general")
        assert os.environ.get(BACKLOG_REDUCTION_MODE_ENV) == "1"
        assert configured_max_active() == 0
        return {"status": "ok", "bound": [], "adopted": [], "deferred": []}

    class Processor:
        def cycle(self) -> dict:
            calls.append("cycle")
            return {"status": "ok"}

    monkeypatch.delenv(BACKLOG_REDUCTION_MODE_ENV, raising=False)
    monkeypatch.setattr(task_router, "route_capability_growth", forbidden_capability)
    monkeypatch.setattr(task_router, "route_self_improvement", forbidden_self_improvement)
    monkeypatch.setattr(task_router, "route_existing_self_improvement", drain_existing)
    monkeypatch.setattr(task_router, "dedupe_self_improvement", dedupe)
    monkeypatch.setattr(task_router, "route_unbacked_tasks", general_router)
    monkeypatch.setattr(task_router, "GenesisCoreProcessor", lambda _root: Processor())

    result = task_router.route_tasks(tmp_path, open_issue_count=84)

    assert calls == ["drain", "dedupe", "general", "cycle"]
    assert result["backlog_reduction"]["active"] is True
    assert result["backlog_reduction"]["high_water"] == 40
    assert result["capability_issue_router"]["status"] == "deferred_backlog_reduction"
    assert result["self_improvement_issue_router"]["status"] == "drain_existing_only"
    assert BACKLOG_REDUCTION_MODE_ENV not in os.environ


def test_task_router_runs_normal_publishers_below_high_water(tmp_path: Path, monkeypatch) -> None:
    calls: list[str] = []

    def forbidden_drain(_root: Path) -> dict:
        raise AssertionError("existing-only drain is for backlog reduction mode")

    monkeypatch.delenv(BACKLOG_REDUCTION_MODE_ENV, raising=False)
    monkeypatch.setattr(task_router, "route_capability_growth", lambda _root: calls.append("capability") or {"status": "ok"})
    monkeypatch.setattr(task_router, "route_self_improvement", lambda _root: calls.append("self") or {"status": "ok"})
    monkeypatch.setattr(task_router, "route_existing_self_improvement", forbidden_drain)
    monkeypatch.setattr(task_router, "dedupe_self_improvement", lambda _root: calls.append("dedupe") or {"status": "ok"})
    monkeypatch.setattr(task_router, "route_unbacked_tasks", lambda _root: calls.append("general") or {"status": "ok"})

    class Processor:
        def cycle(self) -> dict:
            calls.append("cycle")
            return {"status": "ok"}

    monkeypatch.setattr(task_router, "GenesisCoreProcessor", lambda _root: Processor())

    result = task_router.route_tasks(tmp_path, open_issue_count=39)

    assert calls == ["capability", "self", "dedupe", "general", "cycle"]
    assert result["backlog_reduction"]["active"] is False


def test_worker_pool_drains_repairs_before_low_priority_improvements() -> None:
    issues = [
        _issue(10, "[Genesis Self Improvement] planned self improvement — old", "2026-01-01T00:00:00Z"),
        _issue(11, "[Genesis Task] frontier benchmark measurement — old", "2026-01-02T00:00:00Z"),
        _issue(12, "[Genesis Task] self repair — newer", "2026-08-01T00:00:00Z"),
        _issue(13, "[Genesis Repair] repair throughput blocker", "2026-08-02T00:00:00Z"),
        _issue(14, "Genesis challenge: medium priority", "2026-01-03T00:00:00Z"),
    ]

    batch = select_issue_repair_batch(issues, max_parallel=3)

    assert batch.selected_issue_numbers == (12, 13, 14)
