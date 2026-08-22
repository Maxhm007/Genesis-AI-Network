from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class AgenticPlan:
    goal_id: str
    objective: str
    next_action: str
    specialist: str
    reason: str
    expected_signal: str
    strategy: str
    step_budget: int


class AgenticPulseController:
    """Persistent goal/plan/act/observe/replan state for one Genesis Gene.

    The controller does not bypass Genesis' existing engineering, review,
    validation, or promotion gates. It adds a durable decision layer around
    those bounded workers so each Pulse has an explicit goal, expected outcome,
    observation, and next intention.
    """

    VERSION = 1
    MAX_OBSERVATIONS = 50
    DEFAULT_STEP_BUDGET = 12

    _STAGE_INTENTS = {
        "promoted": ("learn", "learning", "task_closed_or_learning_recorded"),
        "review_ready": ("review_candidate", "review", "review_decision_recorded"),
        "needs_development_revision": (
            "revise_development",
            "development",
            "candidate_or_revision_feedback_recorded",
        ),
        "needs_repair": ("revise_repair", "repair", "candidate_or_repair_feedback_recorded"),
        "development_ready": ("develop_capability", "development", "candidate_created_or_feedback_recorded"),
        "repair_ready": ("repair_issue", "repair", "candidate_created_or_feedback_recorded"),
        "discovered": ("triage_issue", "triage", "triage_decision_recorded"),
        "validation_ready": ("observe_validation", "validation", "promotion_or_wait_recorded"),
    }

    _PROGRESS_ACTIONS = {
        "pipeline_issue_discovered",
        "pipeline_triaged",
        "pipeline_development_triaged",
        "pipeline_development_completed",
        "pipeline_repair_completed",
        "pipeline_internal_review_approved",
        "pipeline_promotion_observed",
        "pipeline_learning_completed",
        "promotion_observed_reassess",
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
        self.path = self.root / "runtime" / "grce" / logical_id / "agentic_state.json"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.state = self._load()

    def _default_state(self) -> dict[str, Any]:
        return {
            "version": self.VERSION,
            "logical_id": self.logical_id,
            "goal": {},
            "plan": {},
            "observations": [],
            "metrics": {
                "steps": 0,
                "progress_events": 0,
                "failure_events": 0,
                "wait_events": 0,
                "replans": 0,
                "stall_events": 0,
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
        state["logical_id"] = self.logical_id
        state["version"] = self.VERSION
        if not isinstance(state.get("metrics"), dict):
            state["metrics"] = self._default_state()["metrics"]
        if not isinstance(state.get("observations"), list):
            state["observations"] = []
        return state

    def _save(self) -> None:
        self.state["updated_at"] = utc_now()
        self.path.write_text(
            json.dumps(self.state, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    @staticmethod
    def _record_sort_key(record: Any) -> tuple[str, str]:
        return (str(getattr(record, "updated_at", "")), str(getattr(record, "task_id", "")))

    def _select_record(self, active: list[Any]) -> Any | None:
        # Mirror the bounded pipeline's executable priority. Validation waits are
        # deliberately last so a waiting candidate cannot starve local work.
        priority = (
            "promoted",
            "review_ready",
            "needs_development_revision",
            "needs_repair",
            "development_ready",
            "repair_ready",
            "discovered",
            "validation_ready",
        )
        for stage in priority:
            matches = sorted(
                (record for record in active if getattr(record, "stage", None) == stage),
                key=self._record_sort_key,
            )
            if matches:
                return matches[0]
        return None

    def _goal_for(self, record: Any | None) -> dict[str, Any]:
        now = utc_now()
        if record is None:
            goal_id = "genesis:self-improvement"
            objective = (
                "Continuously improve Genesis by discovering the highest-confidence actionable issue, "
                "repairing or developing it through independent review and validation, learning from the "
                "outcome, and then reassessing the repository."
            )
            target = None
        else:
            task_id = str(getattr(record, "task_id", "unknown"))
            target = str(getattr(record, "target_path", "") or "")
            goal_id = f"pipeline:{task_id}"
            objective = f"Complete Genesis pipeline task {task_id}"
            if target:
                objective += f" for {target}"
            objective += " without bypassing review, validation, promotion, or scope controls."

        current = dict(self.state.get("goal") or {})
        if current.get("goal_id") == goal_id:
            return current
        return {
            "goal_id": goal_id,
            "objective": objective,
            "target": target,
            "status": "active",
            "created_at": now,
            "success_criteria": [
                "bounded worker action completes",
                "independent review and validation gates remain intact",
                "result is persisted so the next Pulse can continue",
            ],
        }

    def _strategy(self) -> str:
        observations = list(self.state.get("observations") or [])
        if observations:
            last = observations[-1]
            if last.get("classification") == "failure":
                return "use_feedback_and_retry_same_goal"
            if last.get("classification") == "stalled":
                return "reassess_worker_and_evidence_before_retry"
            if last.get("classification") == "waiting":
                return "preserve_goal_and_work_other_executable_items"
        return "advance_highest_priority_bounded_step"

    def plan(self, pipeline: Any) -> AgenticPlan:
        active = list(pipeline.store.list_active())
        record = self._select_record(active)
        goal = self._goal_for(record)
        self.state["goal"] = goal

        if record is None:
            next_action = "discover_or_learn"
            specialist = "discovery"
            reason = "no active pipeline task has executable work"
            expected_signal = "new_issue_or_learning_checkpoint"
        else:
            stage = str(getattr(record, "stage", ""))
            next_action, specialist, expected_signal = self._STAGE_INTENTS.get(
                stage,
                ("reassess_pipeline", "coordinator", "pipeline_state_changed"),
            )
            reason = f"oldest highest-priority active stage is {stage}"

        plan = AgenticPlan(
            goal_id=str(goal["goal_id"]),
            objective=str(goal["objective"]),
            next_action=next_action,
            specialist=specialist,
            reason=reason,
            expected_signal=expected_signal,
            strategy=self._strategy(),
            step_budget=self.DEFAULT_STEP_BUDGET,
        )
        self.state["plan"] = asdict(plan)
        self._save()
        return plan

    @staticmethod
    def _result_record(result: dict[str, Any]) -> dict[str, Any]:
        pipeline = dict(result.get("pipeline") or {})
        record = dict(pipeline.get("record") or result.get("record") or {})
        if not record and isinstance(pipeline.get("validation_waits"), list) and pipeline["validation_waits"]:
            record = dict(pipeline["validation_waits"][0].get("record") or {})
        return record

    def _classify(self, action: str) -> str:
        if action in self._PROGRESS_ACTIONS:
            return "progress"
        if action in self._FAILURE_ACTIONS:
            return "failure"
        if action in {"pipeline_wait_validation", "hold_focus_while_validation_finishes"}:
            return "waiting"
        if action in {"fatal_stop", "owner_stop"}:
            return "stopped"
        return "neutral"

    def _is_stalled(self, signature: str) -> bool:
        observations = list(self.state.get("observations") or [])
        recent = [str(item.get("signature") or "") for item in observations[-2:]]
        return len(recent) == 2 and all(item == signature for item in recent)

    @staticmethod
    def _next_intent(action: str) -> str:
        mapping = {
            "pipeline_issue_discovered": "triage_issue",
            "pipeline_triaged": "repair_issue",
            "pipeline_development_triaged": "develop_capability",
            "pipeline_development_completed": "review_candidate",
            "pipeline_repair_completed": "review_candidate",
            "pipeline_development_retry": "revise_development",
            "pipeline_repair_retry": "revise_repair",
            "pipeline_internal_review_needs_development": "revise_development",
            "pipeline_internal_review_needs_repair": "revise_repair",
            "pipeline_internal_review_approved": "observe_validation",
            "pipeline_wait_validation": "preserve_goal_wait_validation",
            "pipeline_promotion_observed": "learn_from_promotion",
            "pipeline_learning_completed": "discover_or_learn",
            "pipeline_quarantined": "reassess_other_work",
            "pipeline_discovery_continue": "continue_discovery",
            "learn_discover_reassess": "reassess_after_learning",
        }
        return mapping.get(action, "reassess_from_observation")

    def observe(self, result: dict[str, Any]) -> dict[str, Any]:
        action = str(result.get("action") or "unknown")
        record = self._result_record(result)
        task_id = record.get("task_id") or dict(result.get("decision") or {}).get("task_id")
        stage = record.get("stage")
        signature = f"{action}|{task_id or ''}|{stage or ''}"
        classification = self._classify(action)
        stalled = self._is_stalled(signature)
        if stalled and classification not in {"progress", "stopped"}:
            classification = "stalled"

        observation = {
            "at": utc_now(),
            "action": action,
            "task_id": task_id,
            "stage": stage,
            "classification": classification,
            "signature": signature,
            "next_intent": self._next_intent(action),
        }

        observations = list(self.state.get("observations") or [])
        observations.append(observation)
        self.state["observations"] = observations[-self.MAX_OBSERVATIONS :]

        metrics = dict(self.state.get("metrics") or {})
        metrics["steps"] = int(metrics.get("steps", 0)) + 1
        if classification == "progress":
            metrics["progress_events"] = int(metrics.get("progress_events", 0)) + 1
        elif classification == "failure":
            metrics["failure_events"] = int(metrics.get("failure_events", 0)) + 1
            metrics["replans"] = int(metrics.get("replans", 0)) + 1
        elif classification == "waiting":
            metrics["wait_events"] = int(metrics.get("wait_events", 0)) + 1
        elif classification == "stalled":
            metrics["stall_events"] = int(metrics.get("stall_events", 0)) + 1
            metrics["replans"] = int(metrics.get("replans", 0)) + 1
        self.state["metrics"] = metrics

        if action in {"pipeline_learning_completed", "promotion_observed_reassess"}:
            goal = dict(self.state.get("goal") or {})
            if goal:
                goal["status"] = "completed"
                goal["completed_at"] = utc_now()
                self.state["goal"] = goal
        elif classification in {"failure", "stalled"}:
            plan = dict(self.state.get("plan") or {})
            plan["strategy"] = (
                "reassess_worker_and_evidence_before_retry"
                if classification == "stalled"
                else "use_feedback_and_retry_same_goal"
            )
            plan["replan_reason"] = f"{classification}:{action}"
            self.state["plan"] = plan

        self._save()
        return {
            "goal": dict(self.state.get("goal") or {}),
            "plan": dict(self.state.get("plan") or {}),
            "observation": observation,
            "metrics": dict(self.state.get("metrics") or {}),
        }

    def snapshot(self) -> dict[str, Any]:
        return {
            "goal": dict(self.state.get("goal") or {}),
            "plan": dict(self.state.get("plan") or {}),
            "metrics": dict(self.state.get("metrics") or {}),
            "recent_observations": list(self.state.get("observations") or [])[-5:],
        }
