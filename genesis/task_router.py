from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path

from .job_failure import JobFailureIntelligence
from .modules.task_queue import GenesisTask, PersistentTaskQueue


MODULE_RULES: tuple[tuple[tuple[str, ...], str], ...] = (
    (("security", "vulnerability", "secret", "attack", "auth"), "genesis.security"),
    (("model", "provider", "inference", "reasoning", "benchmark model"), "genesis.model_scout"),
    (("research", "paper", "study", "evidence", "aging", "longevity", "immortality"), "genesis.research"),
    (("blockchain", "consensus", "peer", "distributed", "replication", "network"), "genesis.blockchain"),
    (("android", "desktop", "application", "apk", "windows", "ui"), "genesis.application"),
    (("memory", "lesson", "knowledge", "recall"), "genesis.memory"),
    (("update", "upgrade", "promotion", "release candidate"), "genesis.updater"),
    (("code", "coding", "bug", "fix", "repair", "refactor", "test failure"), "genesis.coding"),
)

TEAM_HINTS = (
    "cross-module",
    "multi-module",
    "high risk",
    "critical",
    "architecture",
    "tradeoff",
    "disputed",
    "unknown root cause",
)

PENDING_STATES = ("new", "assigned", "running", "paused", "blocked", "review", "failed", "quarantined")
ACTIVE_STATES = ("assigned", "running", "review")
ACTIVE_TASK_LIMIT = 3


@dataclass(frozen=True)
class RouteDecision:
    task_id: str
    module_id: str
    use_ai_team: bool
    reason: str

    def as_dict(self) -> dict:
        return asdict(self)


class TaskRouterModule:
    """Maintain up to three durable Genesis work slots without cancelling active work.

    Each slot keeps its task until completion, pause/hold, blocking, or explicit
    reasoned cancellation. New tasks are assigned only when an active slot is free.
    """

    def __init__(self, root: Path) -> None:
        self.root = Path(root).resolve()
        self.runtime = self.root / "runtime"
        self.runtime.mkdir(parents=True, exist_ok=True)
        self.queue = PersistentTaskQueue(self.runtime / "genesis_tasks.sqlite3")
        self.todo_path = self.runtime / "todo.json"
        self.last_route_path = self.runtime / "task_route.json"

    @staticmethod
    def route(task: GenesisTask) -> RouteDecision:
        recovery = JobFailureIntelligence.plan(task) if task.state == "failed" else None

        if recovery and recovery.module_id:
            module_id = recovery.module_id
            reason = f"job failure recovery selected {module_id}: {recovery.reason}"
        elif task.module_id:
            module_id = task.module_id
            reason = "task already has explicit module ownership"
        else:
            text = f"{task.objective}\n{json.dumps(task.payload, sort_keys=True)}".lower()
            module_id = "genesis.automation"
            reason = "no specialist keyword matched; automation retains triage ownership"
            for keywords, candidate in MODULE_RULES:
                if any(keyword in text for keyword in keywords):
                    module_id = candidate
                    reason = f"matched task domain for {candidate}"
                    break

        text = f"{task.objective}\n{json.dumps(task.payload, sort_keys=True)}".lower()
        explicit_team = bool(task.payload.get("use_ai_team") or task.payload.get("cross_module"))
        matched_domains = sum(1 for keywords, _ in MODULE_RULES if any(keyword in text for keyword in keywords))
        use_ai_team = explicit_team or matched_domains >= 2 or any(hint in text for hint in TEAM_HINTS)
        if recovery:
            use_ai_team = use_ai_team or recovery.use_ai_team
            if recovery.recruit_specialist:
                reason += "; dynamic specialist recruitment requested"
        if use_ai_team and "AI Team" not in reason:
            reason += "; AI Team requested for complex/cross-module coordination"
        return RouteDecision(task.task_id, module_id, use_ai_team, reason)

    def pending(self, limit: int = 200) -> list[GenesisTask]:
        tasks = self.queue.list(limit=limit)
        return [task for task in tasks if task.state in PENDING_STATES]

    def active(self) -> list[GenesisTask]:
        return [task for task in self.pending() if task.state in ACTIVE_STATES]

    def write_todo(self) -> dict:
        tasks = self.pending()
        active = [task for task in tasks if task.state in ACTIVE_STATES]
        payload = {
            "pending": len(tasks),
            "active": len(active),
            "active_limit": ACTIVE_TASK_LIMIT,
            "active_task_ids": [task.task_id for task in active],
            "tasks": [asdict(task) for task in tasks],
            "rule": (
                "Keep at most three persistent active tasks. Running work is never auto-cancelled. "
                "Paused/held work remains durable and resumable. Cancellation requires an explicit recorded reason. "
                "Failed jobs retry only after backoff; repeated failures switch recovery strategy; exhausted jobs are quarantined."
            ),
        }
        self.todo_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return payload

    def assign_next(self) -> dict:
        self.write_todo()
        active = self.active()
        if len(active) >= ACTIVE_TASK_LIMIT:
            result = {
                "status": "active_slots_full",
                "decision": None,
                "active": len(active),
                "active_limit": ACTIVE_TASK_LIMIT,
                "active_task_ids": [task.task_id for task in active],
            }
            self.last_route_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            return result

        candidates = [
            task for task in self.pending()
            if task.state == "new" or self.queue.retryable(task)
        ]
        if not candidates:
            result = {
                "status": "idle",
                "decision": None,
                "active": len(active),
                "active_limit": ACTIVE_TASK_LIMIT,
            }
            self.last_route_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            return result

        task = candidates[0]
        decision = self.route(task)
        recovery = JobFailureIntelligence.plan(task) if task.state == "failed" else None
        assigned = self.queue.transition(task.task_id, "assigned", module_id=decision.module_id)
        result = {
            "status": "assigned",
            "decision": decision.as_dict(),
            "task": asdict(assigned),
            "active": len(active) + 1,
            "active_limit": ACTIVE_TASK_LIMIT,
            "ai_team_module": "genesis.ai_team" if decision.use_ai_team else None,
            "recovery_plan": recovery.as_dict() if recovery else None,
        }
        self.last_route_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        self.write_todo()
        return result
