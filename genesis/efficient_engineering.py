from __future__ import annotations

import json
import time
from dataclasses import asdict, replace

from .autonomous_engineering import ENGINEERING_MODULES, AutonomousEngineeringLoop
from .development_efficiency import DevelopmentEfficiencyGovernor
from .devlab.module import GenesisDevLab
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
        self.devlab = GenesisDevLab(self.root, self.providers)
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

    def _attempt_devlab_task(self, task, runtime) -> dict:
        """Execute an explicitly marked task through DevLab without self-approval."""
        started = time.perf_counter()
        owner_module = task.module_id or "genesis.coding"
        target_path = str(task.payload.get("target_path") or "").replace("\\", "/").lstrip("./")
        attempt = {
            "task": asdict(task),
            "owner_module": owner_module,
            "executor_module": "genesis.devlab",
            "ai_team_context_used": False,
            "context_paths": [target_path] if target_path else [],
            "candidate_revisions": 0,
            "coding_status": "started",
            "candidate": None,
            "candidate_security": None,
            "self_evaluation_context_used": False,
            "self_evaluation_context_bytes": 0,
        }
        provider_name = "unknown"
        try:
            if not target_path or not (self.root / target_path).is_file():
                raise RuntimeError("DevLab task requires an existing target_path")
            if task.state != "assigned":
                self.queue.transition(task.task_id, "assigned", module_id=owner_module)
            self.queue.transition(task.task_id, "running", module_id=owner_module)
            provider = self.coding._provider()
            if provider is None:
                raise RuntimeError("no intelligence provider available")
            provider_name = provider.name
            result = self.devlab.attempt_problem(
                target_path=target_path,
                problem=task.objective,
                acceptance=str(task.payload.get("acceptance") or task.objective),
                provider=provider,
                provenance={
                    "initiator": "owner",
                    "designer": "genesis.devlab",
                    "executor": "genesis.devlab",
                    "source_task_id": task.task_id,
                    "attribution": "owner_initiated",
                },
            )
            feedback = result.feedback
            attempt["devlab"] = result.as_dict()
            attempt["candidate"] = {
                "committed": bool(feedback and feedback.candidate_created),
                "tests_passed": bool(feedback and feedback.tests_passed),
                "commit_sha": feedback.commit_sha if feedback else None,
                "branch": feedback.branch if feedback else "",
                "changed_files": [target_path] if feedback and feedback.candidate_created else [],
                "message": feedback.failure if feedback else result.status,
            }
            if not feedback or not feedback.candidate_created or not feedback.tests_passed:
                attempt["coding_status"] = "candidate_not_committed"
                self.queue.transition(task.task_id, "blocked", module_id=owner_module)
                self._record_efficiency(provider_name, started, False, task_type="devlab_issue")
                return attempt

            candidate_security = self.security.write_report(
                runtime / "candidate_security_report.json", candidate=True, base_ref="main"
            )
            attempt["candidate_security"] = candidate_security
            if candidate_security["status"] != "pass":
                attempt["coding_status"] = "candidate_rejected_by_security"
                self._git("checkout", "main")
                self.queue.transition(task.task_id, "blocked", module_id=owner_module)
                self._record_efficiency(provider_name, started, False, task_type="devlab_issue")
                return attempt

            attempt["coding_status"] = "candidate_created"
            self.queue.transition(task.task_id, "review", module_id=owner_module)
            self._record_efficiency(provider_name, started, True, task_type="devlab_issue")
            return attempt
        except Exception as exc:
            attempt["coding_status"] = "provider_or_candidate_error"
            attempt["error"] = f"{type(exc).__name__}: {exc}"[:2000]
            current = self.queue.get(task.task_id)
            if current and current.state in {"assigned", "running"}:
                try:
                    self.queue.transition(task.task_id, "blocked", module_id=owner_module)
                except Exception:
                    pass
            if provider_name != "unknown":
                try:
                    self._record_efficiency(provider_name, started, False, task_type="devlab_issue")
                except Exception:
                    pass
            return attempt

    def _attempt_task(self, task, runtime) -> dict:
        if str(task.payload.get("executor") or "") == "genesis.devlab":
            return self._attempt_devlab_task(task, runtime)

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
