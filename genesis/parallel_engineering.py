from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from .autonomous_engineering import ENGINEERING_MODULES, AutonomousEngineeringLoop
from .development_efficiency import DevelopmentEfficiencyGovernor
from .modules.task_queue import PersistentTaskQueue
from .velocity import AdaptiveVelocityController, GeneVelocity


SERIAL_ONLY_MODULES = {
    "genesis.security",
    "genesis.blockchain",
    "genesis.updater",
    "genesis.self_development",
}


@dataclass(frozen=True)
class ParallelTask:
    rank: int
    task_id: str
    module_id: str
    objective: str
    score: float


class ParallelDevelopmentPlanner:
    """Select at most two independent, low-risk engineering tasks for isolated workers."""

    MAX_PARALLEL = 2

    def __init__(self, root: Path) -> None:
        self.root = Path(root).resolve()
        self.queue = PersistentTaskQueue(self.root / "runtime" / "genesis_tasks.sqlite3")
        self.governor = DevelopmentEfficiencyGovernor(self.queue)
        self.velocity_policy = AdaptiveVelocityController(self.root).policy()
        self.velocity_report = GeneVelocity(self.root).report()

    def capacity(self) -> int:
        risk_events = int(self.velocity_policy.get("recent_risk_events", 0) or 0)
        if risk_events:
            return 1
        earned = int(self.velocity_policy.get("recommended_parallel_candidates", 1) or 1)
        validated = int(self.velocity_report.get("validated_updates_24h", 0) or 0)
        if validated >= 4:
            earned = max(earned, 2)
        return max(1, min(self.MAX_PARALLEL, earned))

    @staticmethod
    def _scope(task) -> set[str]:
        scope = {f"module:{task.module_id}"}
        for path in AutonomousEngineeringLoop.MODULE_CONTEXT.get(task.module_id or "", ()):  # bounded known context
            scope.add(f"path:{path}")
        for path in task.payload.get("context_paths", []) or []:
            scope.add(f"path:{str(path).replace('\\\\', '/').lstrip('./')}")
        return scope

    def plan(self) -> dict:
        candidates = []
        for state in ("assigned", "new", "failed", "blocked"):
            for task in self.queue.list(state=state, limit=100):
                if task.module_id in ENGINEERING_MODULES:
                    candidates.append(task)
        ranked = self.governor.rank(candidates)
        capacity = self.capacity()
        selected: list[ParallelTask] = []
        used_scope: set[str] = set()

        for task, decision in ranked:
            if len(selected) >= capacity:
                break
            module_id = task.module_id or ""
            if selected and (module_id in SERIAL_ONLY_MODULES or any(item.module_id in SERIAL_ONLY_MODULES for item in selected)):
                continue
            scope = self._scope(task)
            if used_scope.intersection(scope):
                continue
            selected.append(ParallelTask(len(selected), task.task_id, module_id, task.objective, decision.score))
            used_scope.update(scope)
            if module_id in SERIAL_ONLY_MODULES:
                break

        report = {
            "capacity": capacity,
            "tasks": [asdict(item) for item in selected],
            "velocity_policy": self.velocity_policy,
            "velocity_report": self.velocity_report,
            "serial_only_modules": sorted(SERIAL_ONLY_MODULES),
            "promotion_policy": "candidate generation and validation may run in parallel; promotion remains serial exact-head",
        }
        runtime = self.root / "runtime"
        runtime.mkdir(parents=True, exist_ok=True)
        (runtime / "parallel_plan.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return report


def reconcile_parallel_results(root: Path, results: list[dict], promotion: dict | None) -> dict:
    """Persist only terminal outcomes from isolated workers back into the shared queue."""
    root = Path(root).resolve()
    queue = PersistentTaskQueue(root / "runtime" / "genesis_tasks.sqlite3")
    promoted_task = str((promotion or {}).get("task_id") or "")
    actions: list[dict] = []

    for result in results:
        task_data = result.get("selected_task") or {}
        task_id = str(task_data.get("task_id") or "")
        if not task_id:
            continue
        current = queue.get(task_id)
        if current is None:
            actions.append({"task_id": task_id, "action": "missing"})
            continue
        status = str(result.get("coding_status") or "unknown")
        if task_id == promoted_task:
            try:
                if current.state in {"new", "failed", "blocked", "paused", "quarantined"}:
                    queue.transition(task_id, "assigned", module_id=current.module_id)
                    current = queue.get(task_id)
                if current and current.state == "assigned":
                    queue.transition(task_id, "running", module_id=current.module_id)
                    current = queue.get(task_id)
                if current and current.state == "running":
                    queue.transition(task_id, "review", module_id=current.module_id)
                    current = queue.get(task_id)
                if current and current.state == "review":
                    queue.transition(task_id, "complete", module_id=current.module_id)
                actions.append({"task_id": task_id, "action": "complete_after_serial_promotion"})
            except Exception as exc:
                actions.append({"task_id": task_id, "action": "reconcile_error", "error": str(exc)[:500]})
        elif status not in {"candidate_created"}:
            try:
                queue.record_failure(
                    task_id,
                    f"parallel worker ended with {status}",
                    classification="parallel_candidate_failure",
                    retry_after_seconds=900,
                    module_id=current.module_id,
                )
                actions.append({"task_id": task_id, "action": "cooldown_after_failure"})
            except Exception as exc:
                actions.append({"task_id": task_id, "action": "failure_not_recorded", "error": str(exc)[:500]})
        else:
            actions.append({"task_id": task_id, "action": "validated_candidate_waits_for_serial_rebase_or_next_cycle"})

    report = {"promotion": promotion or {}, "actions": actions}
    (root / "runtime" / "parallel_reconcile.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report
