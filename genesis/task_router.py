from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path

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

PENDING_STATES = ("new", "assigned", "running", "blocked", "review", "failed")


@dataclass(frozen=True)
class RouteDecision:
    task_id: str
    module_id: str
    use_ai_team: bool
    reason: str

    def as_dict(self) -> dict:
        return asdict(self)


class TaskRouterModule:
    """Assign one durable Genesis task at a time to the most relevant module.

    Unresolved tasks remain in the persistent SQLite task queue and are exposed
    as a TODO snapshot. AI Team is reserved for complex/cross-module work; it is
    not a replacement for normal module ownership.
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
        if task.module_id:
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
        if use_ai_team:
            reason += "; AI Team requested for complex/cross-module coordination"
        return RouteDecision(task.task_id, module_id, use_ai_team, reason)

    def pending(self, limit: int = 200) -> list[GenesisTask]:
        tasks = self.queue.list(limit=limit)
        return [task for task in tasks if task.state in PENDING_STATES]

    def write_todo(self) -> dict:
        tasks = self.pending()
        payload = {
            "pending": len(tasks),
            "tasks": [asdict(task) for task in tasks],
            "rule": "Pending issues remain durable until explicitly completed. Highest priority and oldest task wins within the same priority.",
        }
        self.todo_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return payload

    def assign_next(self) -> dict:
        self.write_todo()
        candidates = [task for task in self.pending() if task.state in {"new", "failed"}]
        if not candidates:
            result = {"status": "idle", "decision": None}
            self.last_route_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            return result

        task = candidates[0]
        decision = self.route(task)
        if task.state == "failed":
            assigned = self.queue.transition(task.task_id, "assigned", module_id=decision.module_id)
        else:
            assigned = self.queue.transition(task.task_id, "assigned", module_id=decision.module_id)
        result = {
            "status": "assigned",
            "decision": decision.as_dict(),
            "task": asdict(assigned),
            "ai_team_module": "genesis.ai_team" if decision.use_ai_team else None,
        }
        self.last_route_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        self.write_todo()
        return result
