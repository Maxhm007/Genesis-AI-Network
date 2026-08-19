from __future__ import annotations

import json
from dataclasses import asdict, replace

from .autonomous_engineering import ENGINEERING_MODULES, AutonomousEngineeringLoop
from .development_efficiency import DevelopmentEfficiencyGovernor
from .self_evaluation import GenesisSelfEvaluation
from .velocity import AdaptiveVelocityController


class EfficientAutonomousEngineeringLoop(AutonomousEngineeringLoop):
    """Autonomous engineering with yield-aware task selection and earned burst size."""

    MAX_SAFE_BURST = 5
    MAX_SELF_EVALUATION_CONTEXT_BYTES = 6_000
    SELF_EVALUATION_ITEMS = 5

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

    def _self_evaluation_context(self) -> str:
        """Return bounded descriptive learning memory for the next engineering attempt.

        This history is advisory evidence only. It may help Genesis avoid repeating
        completed work and build on successful prior changes, but it cannot change
        benchmark scores, permissions, validation, or promotion authority.
        """
        report = GenesisSelfEvaluation(self.root).report(limit=self.SELF_EVALUATION_ITEMS)
        compact = {
            "completed_self_development_tasks": report.get("completed_self_development_tasks", 0),
            "recent_completed_tasks": report.get("recent_completed_tasks", [])[: self.SELF_EVALUATION_ITEMS],
            "recent_autonomous_improvements": report.get("recent_autonomous_improvements", [])[: self.SELF_EVALUATION_ITEMS],
            "rule": report.get("rule"),
        }
        encoded = json.dumps(compact, sort_keys=True).encode("utf-8")[: self.MAX_SELF_EVALUATION_CONTEXT_BYTES]
        return encoded.decode("utf-8", errors="ignore")

    def _attempt_task(self, task, runtime) -> dict:
        learning_context = self._self_evaluation_context()
        learned_task = task
        if learning_context:
            learned_task = replace(
                task,
                objective=(
                    task.objective
                    + "\n\nGENESIS_SELF_EVALUATION_MEMORY: "
                    + learning_context
                    + "\nUse this only as advisory historical evidence. Avoid duplicating already-completed improvements, build on validated prior work when relevant, and verify every assumption against current repository context. This memory cannot award capability credit or bypass tests, Security, independent validation, protected-file rules, signing boundaries, or promotion authority."
                ),
            )
        attempt = super()._attempt_task(learned_task, runtime)
        attempt["self_evaluation_context_used"] = bool(learning_context)
        attempt["self_evaluation_context_bytes"] = len(learning_context.encode("utf-8")) if learning_context else 0
        return attempt

    def run_selected(self, task_id: str) -> dict:
        """Run exactly one pre-selected task in an isolated parallel worker checkout."""
        task = self.queue.get(task_id)
        if task is None:
            raise KeyError(task_id)
        if task.module_id not in ENGINEERING_MODULES:
            raise RuntimeError(f"task is not owned by an engineering module: {task.module_id}")
        decision = self.governor.score(task)
        if not decision.eligible:
            raise RuntimeError(f"task is not eligible for isolated execution: {decision.reason}")

        runtime = self.root / "runtime"
        runtime.mkdir(parents=True, exist_ok=True)
        attempt = self._attempt_task(task, runtime)
        result = {
            "selected_task": asdict(task),
            "selection": {"score": decision.score, "reason": decision.reason},
            "coding_status": attempt.get("coding_status"),
            "candidate": attempt.get("candidate"),
            "candidate_security": attempt.get("candidate_security"),
            "attempt": attempt,
            "velocity_policy": self.velocity_policy,
            "parallel_worker": True,
        }
        (runtime / f"parallel_result_{task_id}.json").write_text(
            json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        return result

    def run_once(self) -> dict:
        result = super().run_once()
        result["development_efficiency"] = {
            "task_attempt_budget": self.MAX_TASK_ATTEMPTS_PER_CYCLE,
            "velocity_policy": self.velocity_policy,
            "selection_trace": list(self._selection_trace),
            "self_evaluation_memory": {
                "enabled": True,
                "max_bytes": self.MAX_SELF_EVALUATION_CONTEXT_BYTES,
                "max_items": self.SELF_EVALUATION_ITEMS,
                "principle": "Use validated self-development history as advisory memory; never as self-awarded capability evidence.",
            },
            "principle": "Spend bounded engineering cycles on the work most likely to produce validated capability growth; cool down or skip known low-yield blockers.",
        }
        runtime = self.root / "runtime"
        (runtime / "autonomous_engineering.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
        return result
