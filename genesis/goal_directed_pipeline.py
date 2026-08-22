from __future__ import annotations

from typing import Any

from .bounded_autonomy_pipeline import BoundedAutonomyPipelineCoordinator


class GoalDirectedPipelineCoordinator(BoundedAutonomyPipelineCoordinator):
    """Bounded pipeline coordinator with a goal-selected task preference.

    Preference changes scheduling only. The selected record is still executed by
    the canonical triage/development/repair/review/validation/learning workers,
    so goal orchestration cannot bypass scope, review, validation, or promotion.
    """

    _EXECUTABLE_STAGES = {
        "promoted",
        "review_ready",
        "needs_development_revision",
        "needs_repair",
        "development_ready",
        "repair_ready",
        "discovered",
        "validation_ready",
    }

    def _run_record(self, record: Any) -> dict:
        stage = str(record.stage)
        if stage == "promoted":
            return {"handled": True, **self.learning.run(record)}
        if stage == "review_ready":
            return {"handled": True, **self.review.run(record)}
        if stage in {"needs_development_revision", "development_ready"}:
            return {"handled": True, **self.development.run(record)}
        if stage in {"needs_repair", "repair_ready"}:
            return {"handled": True, **self.repair.run(record)}
        if stage == "discovered":
            return {"handled": True, **self.triage.run(record)}
        if stage == "validation_ready":
            return {"handled": True, **self.validation.run(record)}
        return {"handled": False, "action": "goal_selected_stage_not_executable"}

    def run_once(self, preferred_task_id: str | None = None) -> dict:
        preferred_task_id = str(preferred_task_id or "").strip()
        if preferred_task_id:
            active = list(self.store.list_active())
            preferred = next(
                (
                    record
                    for record in active
                    if str(record.task_id) == preferred_task_id
                    and str(record.stage) in self._EXECUTABLE_STAGES
                ),
                None,
            )
            if preferred is not None:
                result = self._run_record(preferred)
                result["goal_directed"] = True
                result["preferred_task_id"] = preferred_task_id
                return result

        result = super().run_once()
        result["goal_directed"] = False
        result["preferred_task_id"] = preferred_task_id or None
        return result
