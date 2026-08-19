from __future__ import annotations

import json

from .autonomous_engineering import ENGINEERING_MODULES, AutonomousEngineeringLoop
from .development_efficiency import DevelopmentEfficiencyGovernor
from .velocity import AdaptiveVelocityController


class EfficientAutonomousEngineeringLoop(AutonomousEngineeringLoop):
    """Autonomous engineering with yield-aware task selection and earned burst size."""

    MAX_SAFE_BURST = 5

    def __init__(self, root, providers=None) -> None:
        super().__init__(root, providers)
        self.governor = DevelopmentEfficiencyGovernor(self.queue)
        self.velocity_policy = AdaptiveVelocityController(self.root).policy()
        earned = int(self.velocity_policy.get("max_development_burst", 1) or 1)
        self.MAX_TASK_ATTEMPTS_PER_CYCLE = max(1, min(self.MAX_SAFE_BURST, earned))
        self._selection_trace: list[dict] = []

    def _select_task(self, attempted: set[str] | None = None):
        attempted = attempted or set()
        candidates = []
        for state in ("assigned", "new", "failed", "blocked"):
            for task in self.queue.list(state=state, limit=100):
                if task.task_id in attempted or task.module_id not in ENGINEERING_MODULES:
                    continue
                candidates.append(task)

        ranked = self.governor.rank(candidates)
        if not ranked:
            self._selection_trace.append({"selected": None, "eligible": 0, "considered": len(candidates)})
            return None

        task, decision = ranked[0]
        self._selection_trace.append({
            "selected": task.task_id,
            "score": decision.score,
            "reason": decision.reason,
            "eligible": len(ranked),
            "considered": len(candidates),
        })
        return task

    def run_once(self) -> dict:
        result = super().run_once()
        result["development_efficiency"] = {
            "task_attempt_budget": self.MAX_TASK_ATTEMPTS_PER_CYCLE,
            "velocity_policy": self.velocity_policy,
            "selection_trace": list(self._selection_trace),
            "principle": "Spend bounded engineering cycles on the work most likely to produce validated capability growth; cool down or skip known low-yield blockers.",
        }
        runtime = self.root / "runtime"
        (runtime / "autonomous_engineering.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
        return result
