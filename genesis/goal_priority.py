from __future__ import annotations

from copy import deepcopy

from .goal_orchestrator import GoalOrchestrator
from .modules.task_queue import PersistentTaskQueue


INSTALL_MARKER = "_genesis_measured_growth_priority_installed"
_ORIGINAL_SELECT_NEXT = GoalOrchestrator.select_next
MAX_QUEUE_PRIORITY_BOOST = 94


def _queue_task(orchestrator: GoalOrchestrator, goal: dict):
    task_id = str(goal.get("task_id") or "").strip()
    if not task_id:
        return None
    db_path = orchestrator.root / "runtime" / "genesis_tasks.sqlite3"
    if not db_path.is_file():
        return None
    try:
        return PersistentTaskQueue(db_path).get(task_id)
    except Exception:
        return None


def _scheduling_metadata(orchestrator: GoalOrchestrator, goal: dict) -> tuple[int, int]:
    """Return effective priority plus a measured-work tie breaker.

    Pipeline stage remains authoritative for completion work: promoted/review work
    retains priority 100/95. Durable queue priority can lift executable work only
    up to 94, directly below review. A validated ``capability_growth`` task wins
    ties over ordinary work, while speculative ``new_capability`` work loses ties.
    """
    base_priority = int(goal.get("priority", 0))
    task = _queue_task(orchestrator, goal)
    if task is None:
        return base_priority, 1

    queue_priority = min(MAX_QUEUE_PRIORITY_BOOST, max(0, int(task.priority)))
    effective_priority = max(base_priority, queue_priority)
    task_type = str((task.payload or {}).get("task_type") or "")
    if task_type == "capability_growth":
        work_rank = 0
    elif task_type == "new_capability":
        work_rank = 2
    else:
        work_rank = 1
    return effective_priority, work_rank


def _select_next_with_measured_growth_priority(self: GoalOrchestrator) -> dict | None:
    candidates = [goal for goal in self.state["goals"].values() if goal.get("status") == "active"]
    candidates.sort(
        key=lambda goal: (
            -_scheduling_metadata(self, goal)[0],
            _scheduling_metadata(self, goal)[1],
            str(goal.get("created_at", "")),
            str(goal.get("goal_id", "")),
        )
    )
    for goal in candidates:
        steps = self._step_map(goal)
        ready = [
            step
            for step in list(goal.get("steps") or [])
            if step.get("status") == "ready" and self._dependencies_complete(step, steps)
        ]
        if not ready:
            continue
        step = ready[0]
        effective_priority, _work_rank = _scheduling_metadata(self, goal)
        return {
            "goal": {
                "goal_id": goal.get("goal_id"),
                "objective": goal.get("objective"),
                "priority": effective_priority,
                "source": goal.get("source"),
                "task_id": goal.get("task_id"),
                "target": goal.get("target"),
            },
            "subtask": deepcopy(step),
            "reason": "highest-priority dependency-ready goal subtask with measured capability growth preference",
        }
    return None


def install_measured_growth_goal_priority() -> None:
    if getattr(GoalOrchestrator, INSTALL_MARKER, False):
        return
    GoalOrchestrator.select_next = _select_next_with_measured_growth_priority
    setattr(GoalOrchestrator, INSTALL_MARKER, True)
