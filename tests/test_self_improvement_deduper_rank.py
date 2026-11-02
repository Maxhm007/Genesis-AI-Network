from __future__ import annotations

from genesis.modules.task_queue import GenesisTask
from genesis.self_improvement_deduper import _canonical_rank


def _task(task_id: str, state: str) -> GenesisTask:
    return GenesisTask(task_id, "fix it", None, state, 0, {}, "2026-11-01T00:00:00Z", "2026-11-01T00:00:00Z")


def test_in_flight_work_ranks_first_so_it_stays_canonical() -> None:
    assert _canonical_rank(_task("a", "pending"), [_task("x", "running")])[0] == 0


def test_active_work_ranks_ahead_of_finished_work() -> None:
    active = _canonical_rank(_task("b", "pending"), [_task("y", "pending")])
    finished = _canonical_rank(_task("c", "pending"), [_task("z", "complete")])
    assert active[0] == 1
    assert finished[0] == 2
    assert active < finished
