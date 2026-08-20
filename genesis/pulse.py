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

    A pulse is deliberately short-lived. Persistent state belongs to the Gene
    runtime/state backend, not to the process executing this class.

    Immediate chaining is reserved for productive executable work. Discovery,
    validation waits, owner stops, and fatal stops checkpoint and yield so Gene
    does not burn compute by repeatedly re-observing unchanged state.
    """

    def __init__(self, root: Path, logical_id: str = "gene-node-1") -> None:
        self.root = Path(root).resolve()
        self.logical_id = logical_id

    @staticmethod
    def _next_pulse_decision(action: str, payload: dict) -> tuple[bool, str]:
        if action in {"fatal_stop", "owner_stop"}:
            return False, action

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

        # Unknown actions fail closed: preserve state and require another event
        # rather than creating an accidental infinite Actions chain.
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
