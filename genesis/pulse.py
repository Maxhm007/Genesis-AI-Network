from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

from scripts.gene_continuous_work import run_step


@dataclass(frozen=True)
class PulseResult:
    logical_id: str
    action: str
    mode: str
    task_id: str | None
    needs_next_pulse: bool
    next_pulse_reason: str
    payload: dict


class GenePulse:
    """Execute one resumable unit of Gene work.

    Each pulse performs at most one bounded autonomy-pipeline transition. Queue
    state survives the process; specialist workers do not need to remain alive.
    Immediate chaining is used only when the next stage has executable work.
    Validation waits and completed discovery cycles checkpoint instead of spinning.
    """

    def __init__(self, root: Path, logical_id: str = "gene-node-1") -> None:
        self.root = Path(root).resolve()
        self.logical_id = logical_id

    @staticmethod
    def _next_pulse_decision(action: str, payload: dict) -> tuple[bool, str]:
        if action in {"fatal_stop", "owner_stop"}:
            return False, action

        pipeline_continue = {
            "pipeline_issue_discovered": "issue_waiting_for_triage",
            "pipeline_discovery_continue": "next_discovery_batch_ready",
            "pipeline_triaged": "triaged_issue_ready_for_repair",
            "pipeline_development_triaged": "approved_upgrade_ready_for_development",
            "pipeline_development_completed": "developed_candidate_waiting_internal_review",
            "pipeline_development_retry": "development_feedback_ready_for_revision",
            "pipeline_repair_completed": "candidate_waiting_internal_review",
            "pipeline_repair_retry": "repair_feedback_ready_for_retry",
            "pipeline_internal_review_needs_development": "review_feedback_returned_to_development",
            "pipeline_internal_review_needs_repair": "review_feedback_returned_to_repair",
            "pipeline_promotion_observed": "validated_promotion_ready_for_learning",
            "pipeline_learning_completed": "learning_recorded_continue_discovery",
            "pipeline_quarantined": "quarantined_issue_continue_other_work",
        }
        if action in pipeline_continue:
            return True, pipeline_continue[action]

        if action == "pipeline_wait_coding_provider":
            return False, "waiting_for_non_qwen_coding_provider"

        if action == "pipeline_wait_development_provider":
            return False, "waiting_for_non_qwen_development_provider"

        if action in {"pipeline_internal_review_approved", "pipeline_wait_validation"}:
            return False, "waiting_for_independent_validation_and_promotion"

        if action == "attempt_focused_issue":
            return True, "focused_issue_has_executable_work"

        if action == "learn_discover_reassess":
            next_decision = dict(payload.get("next_decision", {}) or {})
            if next_decision.get("mode") == "solve_issue" and next_decision.get("task_id"):
                return True, "discovery_created_executable_issue"
            return False, "idle_discovery_checkpointed"

        if action == "promotion_observed_reassess":
            return True, "validated_promotion_observed_continue_discovery"

        if action == "hold_focus_while_validation_finishes":
            return False, "waiting_for_independent_validation"

        if action == "focus_missing_reassess":
            return False, "focus_cleared_for_external_reassessment"

        return False, "unrecognized_action_checkpointed"

    def run(self) -> PulseResult:
        payload = run_step(self.logical_id)
        decision = dict(payload.get("decision", {}) or {})
        action = str(payload.get("action", "unknown"))
        mode = str(decision.get("mode", "unknown"))
        task_id = decision.get("task_id")
        needs_next, reason = self._next_pulse_decision(action, payload)

        return PulseResult(
            logical_id=self.logical_id,
            action=action,
            mode=mode,
            task_id=str(task_id) if task_id else None,
            needs_next_pulse=needs_next,
            next_pulse_reason=reason,
            payload=payload,
        )

    def report(self) -> dict:
        return asdict(self.run())
