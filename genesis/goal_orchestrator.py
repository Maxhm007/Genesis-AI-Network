from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class GoalOrchestrator:
    """Persistent multi-goal decomposition and dependency-aware planning.

    The orchestrator is intentionally planning-only with respect to code changes:
    it never edits, approves, validates, or promotes a candidate. It mirrors the
    existing bounded autonomy pipeline into durable goal graphs, selects the next
    dependency-ready specialist intention, and records outcomes/replans. Actual
    execution remains owned by Genesis' existing queue, workers, review, and
    independent validation gates.
    """

    VERSION = 1
    MAX_HISTORY = 100
    SELF_GOAL_ID = "genesis:self-improvement"
    DEVELOPMENT_SOURCE = "genesis.evolution_learning"

    _STAGE_PRIORITY = {
        "promoted": 100,
        "review_ready": 95,
        "needs_development_revision": 92,
        "needs_repair": 92,
        "development_ready": 88,
        "repair_ready": 88,
        "discovered": 82,
        "validation_ready": 70,
    }

    _ACTION_STEP = {
        "pipeline_issue_discovered": "discover",
        "pipeline_triaged": "triage",
        "pipeline_development_triaged": "triage",
        "pipeline_development_completed": "execute",
        "pipeline_repair_completed": "execute",
        "pipeline_development_retry": "execute",
        "pipeline_repair_retry": "execute",
        "pipeline_internal_review_approved": "review",
        "pipeline_internal_review_needs_development": "review",
        "pipeline_internal_review_needs_repair": "review",
        "pipeline_wait_validation": "validate",
        "pipeline_promotion_observed": "validate",
        "pipeline_learning_completed": "learn",
        "pipeline_quarantined": "execute",
        "pipeline_discovery_continue": "discover",
        "learn_discover_reassess": "discover",
    }

    _FAILURE_ACTIONS = {
        "pipeline_development_retry",
        "pipeline_repair_retry",
        "pipeline_internal_review_needs_development",
        "pipeline_internal_review_needs_repair",
        "pipeline_quarantined",
        "pipeline_wait_coding_provider",
        "pipeline_wait_development_provider",
    }

    def __init__(self, root: Path, logical_id: str) -> None:
        self.root = Path(root).resolve()
        self.logical_id = logical_id
        self.path = self.root / "runtime" / "grce" / logical_id / "goal_orchestrator.json"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.state = self._load()

    def _default_state(self) -> dict[str, Any]:
        return {
            "version": self.VERSION,
            "logical_id": self.logical_id,
            "goals": {},
            "history": [],
            "metrics": {
                "goals_created": 0,
                "goals_completed": 0,
                "goals_blocked": 0,
                "subtasks_completed": 0,
                "replans": 0,
            },
            "updated_at": utc_now(),
        }

    def _load(self) -> dict[str, Any]:
        if not self.path.is_file():
            return self._default_state()
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            return self._default_state()
        if not isinstance(payload, dict):
            return self._default_state()
        state = self._default_state()
        state.update(payload)
        state["version"] = self.VERSION
        state["logical_id"] = self.logical_id
        if not isinstance(state.get("goals"), dict):
            state["goals"] = {}
        if not isinstance(state.get("history"), list):
            state["history"] = []
        if not isinstance(state.get("metrics"), dict):
            state["metrics"] = self._default_state()["metrics"]
        return state

    def _save(self) -> None:
        self.state["updated_at"] = utc_now()
        self.path.write_text(json.dumps(self.state, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    @staticmethod
    def _step(
        step_id: str,
        objective: str,
        specialist: str,
        action: str,
        dependencies: list[str],
    ) -> dict[str, Any]:
        return {
            "step_id": step_id,
            "objective": objective,
            "specialist": specialist,
            "action": action,
            "dependencies": list(dependencies),
            "status": "pending",
            "attempts": 0,
            "last_outcome": None,
            "updated_at": utc_now(),
        }

    def _pipeline_steps(self, *, development: bool) -> list[dict[str, Any]]:
        execution_specialist = "development" if development else "repair"
        execution_action = "develop_capability" if development else "repair_issue"
        return [
            self._step("discover", "Confirm an actionable issue or capability gap", "discovery", "discover_issue", []),
            self._step("triage", "Validate scope, confidence, and execution path", "triage", "triage_issue", ["discover"]),
            self._step(
                "execute",
                "Produce one bounded candidate change",
                execution_specialist,
                execution_action,
                ["triage"],
            ),
            self._step("review", "Perform internal independent review", "review", "review_candidate", ["execute"]),
            self._step("validate", "Observe independent validation and promotion", "validation", "observe_validation", ["review"]),
            self._step("learn", "Record outcome and feed lessons into future work", "learning", "learn_from_outcome", ["validate"]),
        ]

    def _self_steps(self) -> list[dict[str, Any]]:
        return [
            self._step("discover", "Discover the highest-confidence actionable improvement", "discovery", "discover_or_learn", []),
            self._step("triage", "Triage the discovered improvement", "triage", "triage_issue", ["discover"]),
            self._step("execute", "Implement or repair the selected improvement", "coordinator", "execute_bounded_change", ["triage"]),
            self._step("review", "Review the candidate independently", "review", "review_candidate", ["execute"]),
            self._step("validate", "Validate and promote only through independent gates", "validation", "observe_validation", ["review"]),
            self._step("learn", "Persist lessons and reassess Genesis", "learning", "learn_from_outcome", ["validate"]),
        ]

    @staticmethod
    def _step_map(goal: dict[str, Any]) -> dict[str, dict[str, Any]]:
        return {str(step.get("step_id")): step for step in list(goal.get("steps") or [])}

    @staticmethod
    def _set_step_status(step: dict[str, Any], status: str, outcome: str | None = None) -> None:
        step["status"] = status
        step["updated_at"] = utc_now()
        if outcome is not None:
            step["last_outcome"] = outcome

    def _apply_stage(self, goal: dict[str, Any], stage: str) -> None:
        steps = self._step_map(goal)
        order = ["discover", "triage", "execute", "review", "validate", "learn"]
        ready_by_stage = {
            "discovered": "triage",
            "development_ready": "execute",
            "needs_development_revision": "execute",
            "repair_ready": "execute",
            "needs_repair": "execute",
            "review_ready": "review",
            "validation_ready": "validate",
            "promoted": "learn",
        }
        ready = ready_by_stage.get(stage)
        if ready:
            index = order.index(ready)
            for step_id in order[:index]:
                if step_id in steps:
                    self._set_step_status(steps[step_id], "complete")
            if ready in steps:
                self._set_step_status(steps[ready], "ready")
            for step_id in order[index + 1 :]:
                if step_id in steps and steps[step_id].get("status") != "complete":
                    self._set_step_status(steps[step_id], "pending")
        elif stage == "closed":
            for step in steps.values():
                self._set_step_status(step, "complete")
            goal["status"] = "complete"
            goal["completed_at"] = utc_now()
        elif stage == "quarantined":
            for step in steps.values():
                if step.get("status") not in {"complete"}:
                    self._set_step_status(step, "blocked", "pipeline_quarantined")
            goal["status"] = "blocked"
            goal["blocked_at"] = utc_now()

    def _new_pipeline_goal(self, record: Any) -> dict[str, Any]:
        task_id = str(getattr(record, "task_id", "unknown"))
        target = str(getattr(record, "target_path", "") or "")
        discovery = dict(getattr(record, "discovery", {}) or {})
        stage = str(getattr(record, "stage", "discovered"))
        development = bool(
            discovery.get("source") == self.DEVELOPMENT_SOURCE
            or "development" in stage
        )
        objective = f"Complete Genesis pipeline task {task_id}"
        if target:
            objective += f" for {target}"
        objective += " through bounded execution, independent review, validation, promotion, and learning."
        now = utc_now()
        goal = {
            "goal_id": f"pipeline:{task_id}",
            "objective": objective,
            "source": "pipeline",
            "task_id": task_id,
            "target": target or None,
            "priority": self._STAGE_PRIORITY.get(stage, 75),
            "status": "active",
            "created_at": now,
            "updated_at": now,
            "success_criteria": [
                "candidate remains bounded to approved scope",
                "internal review passes",
                "independent validation and promotion are observed",
                "learning is persisted",
            ],
            "steps": self._pipeline_steps(development=development),
            "replans": 0,
        }
        self._apply_stage(goal, stage)
        return goal

    def _new_self_goal(self) -> dict[str, Any]:
        now = utc_now()
        goal = {
            "goal_id": self.SELF_GOAL_ID,
            "objective": (
                "Continuously improve Genesis by discovering the highest-confidence actionable issue, "
                "turning it into bounded work, validating the result independently, learning, and reassessing."
            ),
            "source": "system",
            "task_id": None,
            "target": None,
            "priority": 50,
            "status": "active",
            "created_at": now,
            "updated_at": now,
            "success_criteria": [
                "a meaningful improvement is discovered",
                "the improvement enters bounded execution",
                "review and validation gates remain intact",
                "the outcome is learned before the next reassessment",
            ],
            "steps": self._self_steps(),
            "replans": 0,
        }
        self._set_step_status(goal["steps"][0], "ready")
        return goal

    def _register_goal(self, goal: dict[str, Any]) -> dict[str, Any]:
        goals = self.state["goals"]
        goal_id = str(goal["goal_id"])
        existing = goals.get(goal_id)
        if existing is None:
            goals[goal_id] = goal
            metrics = self.state["metrics"]
            metrics["goals_created"] = int(metrics.get("goals_created", 0)) + 1
            self._history("goal_created", goal_id=goal_id)
            return goal
        return existing

    def _history(self, event: str, **payload: Any) -> None:
        history = list(self.state.get("history") or [])
        history.append({"at": utc_now(), "event": event, **payload})
        self.state["history"] = history[-self.MAX_HISTORY :]

    def _refresh_pipeline_goal(self, goal: dict[str, Any], record: Any) -> None:
        stage = str(getattr(record, "stage", ""))
        goal["priority"] = self._STAGE_PRIORITY.get(stage, int(goal.get("priority", 75)))
        goal["updated_at"] = utc_now()
        if goal.get("status") not in {"complete", "blocked"}:
            goal["status"] = "active"
        self._apply_stage(goal, stage)

    def sync(self, pipeline: Any) -> dict[str, Any]:
        active = list(pipeline.store.list_active())
        active_ids: set[str] = set()
        for record in active:
            goal_id = f"pipeline:{getattr(record, 'task_id', 'unknown')}"
            active_ids.add(goal_id)
            goal = self._register_goal(self._new_pipeline_goal(record))
            self._refresh_pipeline_goal(goal, record)

        self_goal = self._register_goal(self._new_self_goal())
        if active:
            self_goal["priority"] = 40
        else:
            self_goal["priority"] = 50
            self_goal["status"] = "active"
            steps = self._step_map(self_goal)
            if steps.get("discover", {}).get("status") != "complete":
                self._set_step_status(steps["discover"], "ready")

        getter = getattr(pipeline.store, "get", None)
        if callable(getter):
            for goal_id, goal in list(self.state["goals"].items()):
                if goal.get("source") != "pipeline" or goal_id in active_ids:
                    continue
                task_id = str(goal.get("task_id") or "")
                if not task_id:
                    continue
                record = getter(task_id)
                if record is not None:
                    self._refresh_pipeline_goal(goal, record)

        selected = self.select_next()
        self._save()
        return {
            "selected": selected,
            "active_goal_count": sum(1 for goal in self.state["goals"].values() if goal.get("status") == "active"),
            "metrics": dict(self.state.get("metrics") or {}),
        }

    @staticmethod
    def _dependencies_complete(step: dict[str, Any], steps: dict[str, dict[str, Any]]) -> bool:
        return all(steps.get(dep, {}).get("status") == "complete" for dep in list(step.get("dependencies") or []))

    def select_next(self) -> dict[str, Any] | None:
        candidates = [goal for goal in self.state["goals"].values() if goal.get("status") == "active"]
        candidates.sort(key=lambda goal: (-int(goal.get("priority", 0)), str(goal.get("created_at", "")), str(goal.get("goal_id", ""))))
        for goal in candidates:
            steps = self._step_map(goal)
            ready: list[dict[str, Any]] = []
            for step in list(goal.get("steps") or []):
                if step.get("status") == "ready" and self._dependencies_complete(step, steps):
                    ready.append(step)
            if not ready:
                continue
            step = ready[0]
            return {
                "goal": {
                    "goal_id": goal.get("goal_id"),
                    "objective": goal.get("objective"),
                    "priority": goal.get("priority"),
                    "source": goal.get("source"),
                    "task_id": goal.get("task_id"),
                    "target": goal.get("target"),
                },
                "subtask": deepcopy(step),
                "reason": "highest-priority dependency-ready goal subtask",
            }
        return None

    @staticmethod
    def _task_id_from_result(result: dict[str, Any]) -> str | None:
        pipeline = dict(result.get("pipeline") or {})
        record = dict(pipeline.get("record") or result.get("record") or {})
        task_id = record.get("task_id") or dict(result.get("decision") or {}).get("task_id")
        if task_id:
            return str(task_id)
        discovery = dict(pipeline.get("discovery") or result.get("discovery") or {})
        if discovery.get("task_id"):
            return str(discovery["task_id"])
        return None

    def _complete_step(self, goal: dict[str, Any], step_id: str, outcome: str) -> None:
        steps = self._step_map(goal)
        step = steps.get(step_id)
        if step is None:
            return
        was_complete = step.get("status") == "complete"
        self._set_step_status(step, "complete", outcome)
        if not was_complete:
            metrics = self.state["metrics"]
            metrics["subtasks_completed"] = int(metrics.get("subtasks_completed", 0)) + 1
        order = ["discover", "triage", "execute", "review", "validate", "learn"]
        index = order.index(step_id)
        if index + 1 < len(order):
            next_step = steps.get(order[index + 1])
            if next_step is not None and self._dependencies_complete(next_step, steps):
                self._set_step_status(next_step, "ready")
        else:
            if goal.get("status") != "complete":
                goal["status"] = "complete"
                goal["completed_at"] = utc_now()
                metrics = self.state["metrics"]
                metrics["goals_completed"] = int(metrics.get("goals_completed", 0)) + 1
                self._history("goal_completed", goal_id=goal.get("goal_id"))

    def _fail_step(self, goal: dict[str, Any], step_id: str, outcome: str) -> None:
        step = self._step_map(goal).get(step_id)
        if step is None:
            return
        step["attempts"] = int(step.get("attempts", 0)) + 1
        self._set_step_status(step, "ready", outcome)
        goal["replans"] = int(goal.get("replans", 0)) + 1
        metrics = self.state["metrics"]
        metrics["replans"] = int(metrics.get("replans", 0)) + 1
        self._history("goal_replanned", goal_id=goal.get("goal_id"), step_id=step_id, outcome=outcome)

    def observe(self, result: dict[str, Any]) -> dict[str, Any]:
        action = str(result.get("action") or "unknown")
        task_id = self._task_id_from_result(result)
        goal_id = f"pipeline:{task_id}" if task_id else self.SELF_GOAL_ID
        goal = self.state["goals"].get(goal_id)
        if goal is None:
            goal = self.state["goals"].get(self.SELF_GOAL_ID)
        step_id = self._ACTION_STEP.get(action)

        if goal is not None and step_id is not None:
            if action == "pipeline_quarantined":
                step = self._step_map(goal).get(step_id)
                if step is not None:
                    self._set_step_status(step, "blocked", action)
                if goal.get("status") != "blocked":
                    goal["status"] = "blocked"
                    goal["blocked_at"] = utc_now()
                    metrics = self.state["metrics"]
                    metrics["goals_blocked"] = int(metrics.get("goals_blocked", 0)) + 1
            elif action in self._FAILURE_ACTIONS:
                self._fail_step(goal, step_id, action)
                if action.startswith("pipeline_internal_review_needs_"):
                    execute = self._step_map(goal).get("execute")
                    if execute is not None:
                        self._set_step_status(execute, "ready", action)
            elif action == "pipeline_wait_validation":
                step = self._step_map(goal).get("validate")
                if step is not None:
                    self._set_step_status(step, "ready", action)
            elif action in {
                "pipeline_issue_discovered",
                "pipeline_triaged",
                "pipeline_development_triaged",
                "pipeline_development_completed",
                "pipeline_repair_completed",
                "pipeline_internal_review_approved",
                "pipeline_promotion_observed",
                "pipeline_learning_completed",
            }:
                self._complete_step(goal, step_id, action)
            elif action in {"pipeline_discovery_continue", "learn_discover_reassess"}:
                step = self._step_map(goal).get("discover")
                if step is not None and step.get("status") != "complete":
                    self._set_step_status(step, "ready", action)

        self._history("observation", action=action, goal_id=goal.get("goal_id") if goal else None, task_id=task_id)
        selected = self.select_next()
        self._save()
        return {
            "selected": selected,
            "observed_action": action,
            "goal_id": goal.get("goal_id") if goal else None,
            "metrics": dict(self.state.get("metrics") or {}),
        }

    def snapshot(self) -> dict[str, Any]:
        goals = list(self.state["goals"].values())
        goals.sort(key=lambda goal: (-int(goal.get("priority", 0)), str(goal.get("goal_id", ""))))
        return {
            "selected": self.select_next(),
            "goals": deepcopy(goals),
            "metrics": dict(self.state.get("metrics") or {}),
            "recent_history": list(self.state.get("history") or [])[-10:],
        }

    @staticmethod
    def deterministic_goal_id(objective: str) -> str:
        digest = hashlib.sha256(objective.strip().encode("utf-8")).hexdigest()[:16]
        return f"goal:{digest}"
