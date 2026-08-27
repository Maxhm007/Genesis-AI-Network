from __future__ import annotations

import json
pass
from dataclasses import asdict, replace

from .autonomous_engineering import ENGINEERING_MODULES, AutonomousEngineeringLoop
from .development_efficiency import DevelopmentEfficiencyGovernor
from .devlab.module import GenesisDevLab
from .github_issue_task_router import issue_authority_enabled, issue_backed, route_unbacked_tasks
from .self_evaluation import GenesisSelfEvaluation
from .velocity import AdaptiveVelocityController


class EfficientAutonomousEngineeringLoop(AutonomousEngineeringLoop):
    """Autonomous engineering with one preferred Issue-backed development path.

    In the real Genesis runtime, every engineering task must be backed by a GitHub
    Issue before selection or execution. All Issue-backed tasks share one fair
    rotation, while SQLite remains resumable execution/cache state. Successful
    candidates still pass through Security and independent-validator promotion.
    """

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

    @staticmethod
    def _is_devlab_task(task) -> bool:
        return str(task.payload.get("executor") or "") == "genesis.devlab"

    @staticmethod
    def _is_github_backlog_task(task) -> bool:
        return (
            int(task.payload.get("github_issue_number") or 0) > 0
            and str(task.payload.get("task_type") or "") == "github_issue_development"
        )

    @classmethod
    def _is_managed_github_issue_task(cls, task) -> bool:
        """Return whether this task has authoritative GitHub Issue backing."""
        return issue_backed(task)

    @staticmethod
    def _github_issue_fairness_key(task) -> tuple:
        """Order Issue work so older untouched issues run once, then retries rotate fairly."""
        issue_number = int(task.payload.get("github_issue_number") or 0)
        generation = int(task.payload.get("work_generation") or 1)
        untouched_first_generation = generation == 1 and task.attempt_count == 0 and task.state == "new"
        if untouched_first_generation:
            return (0, issue_number, task.created_at, task.task_id)
        return (1, task.updated_at, issue_number, generation, task.task_id)

    def _eligible_task(self, task, attempted: set[str]) -> bool:
        if task.task_id in attempted or task.module_id not in ENGINEERING_MODULES:
            return False
        if issue_authority_enabled(self.root) and not issue_backed(task):
            return False
        if task.state == "failed" and not self.queue.retryable(task):
            return False
        return task.state in {"assigned", "new", "failed", "blocked"}

    def _select_task(self, attempted: set[str] | None = None):
        attempted = attempted or set()
        candidates = []
        for state in ("assigned", "new", "failed", "blocked"):
            for task in self.queue.list(state=state, limit=100):
                if self._eligible_task(task, attempted):
                    candidates.append(task)

        # All Issue-backed autonomous engineering shares one solve-first fair
        # rotation. This includes owner-created Issues, Genesis-created repairs,
        # capability work, self-improvement, and explicit DevLab challenges.
        issue_candidates = [task for task in candidates if self._is_managed_github_issue_task(task)]
        if issue_candidates:
            task = sorted(issue_candidates, key=self._github_issue_fairness_key)[0]
            self._selection_trace.append({
                "selected": task.task_id,
                "score": None,
                "reason": "github_issue_fair_rotation",
                "eligible": len(issue_candidates),
                "considered": len(candidates),
                "issue_number": int(task.payload.get("github_issue_number") or 0),
                "work_generation": int(task.payload.get("work_generation") or 1),
                "devlab": self._is_devlab_task(task),
            })
            return task

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
        """Return bounded descriptive learning memory for the next engineering attempt."""
        report = GenesisSelfEvaluation(self.root).report(limit=self.SELF_EVALUATION_ITEMS)
        compact = {
            "completed_self_development_tasks": report.get("completed_self_development_tasks", 0),
            "recent_completed_tasks": report.get("recent_completed_tasks", [])[: self.SELF_EVALUATION_ITEMS],
            "recent_autonomous_improvements": report.get("recent_autonomous_improvements", [])[: self.SELF_EVALUATION_ITEMS],
            "rule": report.get("rule"),
        }
        encoded = json.dumps(compact, sort_keys=True).encode("utf-8")[: self.MAX_SELF_EVALUATION_CONTEXT_BYTES]
        return encoded.decode("utf-8", errors="ignore")

    def _record_devlab_failure(self, task, owner_module: str, error: str, classification: str) -> None:
        self.queue.record_failure(
            task.task_id,
            error or classification,
            classification=classification,
            retry_after_seconds=0,
            module_id=owner_module,
        )

    def _attempt_devlab_task(self, task, runtime) -> dict:
        """Execute one persistent DevLab method and preserve failure evidence."""
        if issue_authority_enabled(self.root) and not issue_backed(task):
            raise RuntimeError("GitHub Issue is required before DevLab execution")
        started = time.perf_counter()
        owner_module = task.module_id or "genesis.coding"
        target_path = str(task.payload.get("target_path") or "").replace("\\", "/").lstrip("./")
        attempt = {
            "task": asdict(task),
            "owner_module": owner_module,
            "executor_module": "genesis.devlab",
            "development_path": "GitHub Issue -> task state -> DevLab -> candidate -> Security -> validators -> promotion",
            "ai_team_context_used": False,
            "context_paths": [target_path] if target_path else [],
            "candidate_revisions": task.attempt_count,
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
                attempt=task.attempt_count,
                previous_error=str(task.last_error or ""),
                provider=provider,
                provenance={
                    "initiator": "owner" if task.payload.get("attribution") == "owner_initiated" else "genesis",
                    "designer": "genesis.devlab",
                    "executor": "genesis.devlab",
                    "source_task_id": task.task_id,
                    "github_issue_number": int(task.payload.get("github_issue_number") or 0),
                    "attribution": str(task.payload.get("attribution") or "genesis_autonomous"),
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
                error = feedback.failure if feedback else result.status
                attempt["coding_status"] = "candidate_not_committed"
                self._record_devlab_failure(task, owner_module, error, result.status)
                self._record_efficiency(provider_name, started, False, task_type="devlab_issue")
                return attempt

            candidate_security = self.security.write_report(
                runtime / "candidate_security_report.json", candidate=True, base_ref="main"
            )
            attempt["candidate_security"] = candidate_security
            if candidate_security["status"] != "pass":
                attempt["coding_status"] = "candidate_rejected_by_security"
                self._git("checkout", "main")
                self._record_devlab_failure(task, owner_module, "candidate rejected by Security", "security_rejection")
                self._record_efficiency(provider_name, started, False, task_type="devlab_issue")
                return attempt

            attempt["coding_status"] = "candidate_created"
            self.queue.transition(task.task_id, "review", module_id=owner_module)
            self._record_efficiency(provider_name, started, True, task_type="devlab_issue")
            return attempt
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"[:2000]
            attempt["coding_status"] = "provider_or_candidate_error"
            attempt["error"] = error
            current = self.queue.get(task.task_id)
            if current and current.state not in {"complete", "quarantined", "cancelled"}:
                try:
                    self._record_devlab_failure(current, owner_module, error, "provider_or_candidate_error")
                except Exception:
                    pass
            if provider_name != "unknown":
                try:
                    self._record_efficiency(provider_name, started, False, task_type="devlab_issue")
                except Exception:
                    pass
            return attempt

    def _attempt_task(self, task, runtime) -> dict:
        if issue_authority_enabled(self.root) and not issue_backed(task):
            raise RuntimeError("GitHub Issue is required before autonomous engineering execution")
        if self._is_devlab_task(task):
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
        issue_sync = route_unbacked_tasks(self.root)
        task = self.queue.get(task_id)
        if task is None:
            raise KeyError(task_id)
        if issue_authority_enabled(self.root) and not issue_backed(task):
            raise RuntimeError("GitHub Issue is required before isolated autonomous execution")
        if task.module_id not in ENGINEERING_MODULES:
            raise RuntimeError(f"task is not owned by an engineering module: {task.module_id}")
        decision = self.governor.score(task)
        if not decision.eligible and not self._is_devlab_task(task):
            raise RuntimeError(f"task is not eligible for isolated execution: {decision.reason}")

        runtime = self.root / "runtime"
        runtime.mkdir(parents=True, exist_ok=True)
        attempt = self._attempt_task(task, runtime)
        result = {
            "selected_task": asdict(task),
            "selection": {
                "score": decision.score,
                "reason": "github_issue_fair_rotation" if self._is_managed_github_issue_task(task) else decision.reason,
            },
            "coding_status": attempt.get("coding_status"),
            "candidate": attempt.get("candidate"),
            "candidate_security": attempt.get("candidate_security"),
            "attempt": attempt,
            "velocity_policy": self.velocity_policy,
            "parallel_worker": True,
            "github_issue_sync": issue_sync,
        }
        (runtime / f"parallel_result_{task_id}.json").write_text(
            json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        return result

    def run_once(self) -> dict:
        issue_sync_before = route_unbacked_tasks(self.root)
        result = super().run_once()
        issue_sync_after = route_unbacked_tasks(self.root)
        result["github_issue_authority"] = {
            "enforced": issue_authority_enabled(self.root),
            "source_of_truth": "github_issues",
            "sqlite_role": "execution_cache_state",
            "sync_before": issue_sync_before,
            "sync_after": issue_sync_after,
        }
        result["development_efficiency"] = {
            "task_attempt_budget": self.MAX_TASK_ATTEMPTS_PER_CYCLE,
            "velocity_policy": self.velocity_policy,
            "selection_trace": list(self._selection_trace),
            "golden_path": {
                "enabled": True,
                "path": "GitHub Issue -> task state -> DevLab/Coding -> candidate -> Security -> Validator A/B -> promotion -> verify -> learn",
                "all_production_engineering_requires_github_issue": True,
                "devlab_tasks_have_priority": False,
                "all_issue_tasks_share_fair_rotation": True,
                "github_issue_backlog_has_priority_over_background_work": True,
                "older_untouched_issues_get_first_turn": True,
                "issue_retries_rotate_by_least_recent_work": True,
                "failed_methods_persist_across_cycles": True,
            },
            "self_evaluation_memory": {
                "enabled": True,
                "max_bytes": self.MAX_SELF_EVALUATION_CONTEXT_BYTES,
                "max_items": self.SELF_EVALUATION_ITEMS,
                "principle": "Use validated self-development history as advisory memory; never as self-awarded capability evidence.",
            },
            "principle": "GitHub Issues are authoritative; prefer completed validated outcomes over workflow activity, and do not starve older open Issues.",
        }
        runtime = self.root / "runtime"
        (runtime / "autonomous_engineering.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
        return result
