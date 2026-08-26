from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

from scripts.gene_continuous_work import run_step

from .github_issue_task_router import route_unbacked_tasks


DEFAULT_IDLE_DISCOVERY_BURST = 4


@dataclass(frozen=True)
class PulseResult:
    logical_id: str
    action: str
    mode: str
    task_id: str | None
    needs_next_pulse: bool
    next_pulse_reason: str
    payload: dict


def workflow_chain_decision(
    *,
    needs_next_pulse: bool,
    next_pulse_reason: str,
    idle_budget: int,
    default_idle_budget: int = DEFAULT_IDLE_DISCOVERY_BURST,
) -> tuple[bool, int, str]:
    """Decide whether GitHub Actions should dispatch another Gene Pulse."""
    if default_idle_budget < 1:
        raise ValueError("default idle discovery budget must be positive")
    if idle_budget < 0:
        raise ValueError("idle discovery budget cannot be negative")

    if needs_next_pulse:
        return True, default_idle_budget, "executable_work_continues"

    if next_pulse_reason != "idle_discovery_checkpointed":
        return False, idle_budget, "checkpoint_preserved"

    if idle_budget <= 1:
        return False, 0, "idle_discovery_budget_exhausted"

    return True, idle_budget - 1, "bounded_idle_discovery_burst"


class GenePulse:
    """Execute one resumable unit of Issue-backed Gene work.

    GitHub Issues are the authoritative task source. Before any Pulse work runs,
    Genesis binds every non-terminal local queue row to an Issue. If that binding
    cannot be completed, the Pulse fails closed rather than executing an unbacked
    task. A second sync after the bounded step immediately publishes any new task
    discovered during the same Pulse.
    """

    def __init__(self, root: Path, logical_id: str = "gene-node-1") -> None:
        self.root = Path(root).resolve()
        self.logical_id = logical_id

    @staticmethod
    def _next_pulse_decision(action: str, payload: dict) -> tuple[bool, str]:
        if action in {"fatal_stop", "owner_stop"}:
            return False, action

        if action == "github_issue_sync_blocked":
            return False, "github_issue_authority_unavailable"

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
            return False, "waiting_for_eligible_coding_provider"

        if action == "pipeline_wait_development_provider":
            return False, "waiting_for_eligible_development_provider"

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
        issue_sync_before = route_unbacked_tasks(self.root)
        if issue_sync_before.get("blocked"):
            payload = {
                "decision": {
                    "mode": "github_issue_authority",
                    "task_id": None,
                    "reason": "unbacked task execution is forbidden",
                },
                "action": "github_issue_sync_blocked",
                "github_issue_sync_before": issue_sync_before,
                "policy": "No GitHub Issue = no Genesis task execution.",
            }
            return PulseResult(
                logical_id=self.logical_id,
                action="github_issue_sync_blocked",
                mode="github_issue_authority",
                task_id=None,
                needs_next_pulse=False,
                next_pulse_reason="github_issue_authority_unavailable",
                payload=payload,
            )

        payload = run_step(self.logical_id)
        issue_sync_after = route_unbacked_tasks(self.root)
        payload["github_issue_sync_before"] = issue_sync_before
        payload["github_issue_sync_after"] = issue_sync_after
        payload["task_authority"] = "github_issues"

        decision = dict(payload.get("decision", {}) or {})
        action = str(payload.get("action", "unknown"))
        mode = str(decision.get("mode", "unknown"))
        task_id = decision.get("task_id")
        needs_next, reason = self._next_pulse_decision(action, payload)

        if issue_sync_after.get("blocked"):
            needs_next = False
            reason = "github_issue_authority_unavailable"

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
