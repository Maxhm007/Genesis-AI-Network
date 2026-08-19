from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from .modules.task_queue import GenesisTask, PersistentTaskQueue


EXTERNAL_BLOCKER_MARKERS = (
    "external_execution_required",
    "owner_action_required",
    "credential",
    "secret",
    "harbor",
    "sandbox configuration",
    "external prerequisite",
)


@dataclass(frozen=True)
class TaskDecision:
    task_id: str
    eligible: bool
    score: float
    reason: str


class DevelopmentEfficiencyGovernor:
    """Rank engineering work by expected validated progress, not raw retry volume."""

    def __init__(self, queue: PersistentTaskQueue) -> None:
        self.queue = queue

    @staticmethod
    def _blocked_externally(task: GenesisTask) -> bool:
        text = " ".join(
            str(value or "")
            for value in (
                task.state_reason,
                task.last_error,
                task.payload.get("blocker"),
                task.payload.get("reason"),
                task.payload.get("external_blocker"),
            )
        ).lower()
        return any(marker in text for marker in EXTERNAL_BLOCKER_MARKERS)

    def score(self, task: GenesisTask, *, at: datetime | None = None) -> TaskDecision:
        now = at or datetime.now(timezone.utc)
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)

        if task.state in {"quarantined", "cancelled", "complete", "review", "running"}:
            return TaskDecision(task.task_id, False, -1000.0, f"state_{task.state}_not_selectable")
        if task.state == "failed" and not self.queue.retryable(task, at=now):
            return TaskDecision(task.task_id, False, -900.0, "retry_cooldown_active")
        if self._blocked_externally(task):
            return TaskDecision(task.task_id, False, -800.0, "external_or_owner_blocker")

        score = float(task.priority)
        score += {"assigned": 14.0, "new": 10.0, "failed": 2.0, "blocked": -8.0}.get(task.state, 0.0)
        if task.module_id == "genesis.security":
            score += 25.0

        score -= 14.0 * task.attempt_count
        repeated_failures = max(0, len(task.failure_history) - len({item.get("classification") for item in task.failure_history}))
        score -= 8.0 * repeated_failures

        try:
            created = datetime.fromisoformat(task.created_at)
            if created.tzinfo is None:
                created = created.replace(tzinfo=timezone.utc)
            age_hours = max(0.0, (now.astimezone(timezone.utc) - created.astimezone(timezone.utc)).total_seconds() / 3600.0)
            score += min(12.0, age_hours / 6.0)
        except (TypeError, ValueError):
            pass

        return TaskDecision(task.task_id, True, round(score, 3), "eligible")

    def rank(self, tasks: list[GenesisTask], *, at: datetime | None = None) -> list[tuple[GenesisTask, TaskDecision]]:
        ranked: list[tuple[GenesisTask, TaskDecision]] = []
        for task in tasks:
            decision = self.score(task, at=at)
            if decision.eligible:
                ranked.append((task, decision))
        ranked.sort(key=lambda item: (-item[1].score, item[0].created_at, item[0].task_id))
        return ranked
