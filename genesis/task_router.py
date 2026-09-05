from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path

from .github_issue_task_router import issue_authority_enabled, issue_backed, route_unbacked_tasks
from .job_failure import JobFailureIntelligence
from .modules.task_queue import GenesisTask, PersistentTaskQueue
from .problem_solver import AutonomousProblemSolver


MODULE_RULES: tuple[tuple[tuple[str, ...], str], ...] = (
    (("security", "vulnerability", "secret", "attack", "auth"), "genesis.security"),
    ((
        "model",
        "provider",
        "inference",
        "reasoning",
        "benchmark model",
        "speculative decoding",
        "decode context parallel",
        "decode-context parallel",
        "moe",
        "rocm",
        "cuda graph",
        "tensor parallel",
    ), "genesis.model_scout"),
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

    GitHub Issues are the authoritative production task source. SQLite keeps
    execution state, but an unbacked production row is never eligible for dispatch.
    Every assignment cycle first attempts to bind unbacked autonomous work to an
    Issue; GitHub failure therefore fails closed instead of silently restoring the
    legacy local-queue authority. Temporary unit-test roots keep legacy in-memory
    behavior so CI never mutates the real repository by accident.
    """

    def __init__(self, root: Path) -> None:
        self.root = Path(root).resolve()
        self.runtime = self.root / "runtime"
        self.runtime.mkdir(parents=True, exist_ok=True)
        self.queue = PersistentTaskQueue(self.runtime / "genesis_tasks.sqlite3")
        self.problem_solver = AutonomousProblemSolver(self.root)
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
        unbacked = [task.task_id for task in tasks if not issue_backed(task)]
        payload = {
            "pending": len(tasks),
            "active": len(active),
            "active_limit": ACTIVE_TASK_LIMIT,
            "active_task_ids": [task.task_id for task in active],
            "github_issue_authority_enforced": issue_authority_enabled(self.root),
            "github_issue_unbacked_task_ids": unbacked,
            "tasks": [asdict(task) for task in tasks],
            "rule": (
                "GitHub Issues are authoritative in the real Genesis runtime. Every autonomous task must be "
                "Issue-backed before dispatch. SQLite is execution/cache state only. Keep at most three persistent "
                "active tasks. Running work is never auto-cancelled. Paused/held work remains durable and resumable. "
                "Cancellation requires an explicit recorded reason. Failed jobs are diagnosed before retry; repeated "
                "non-transient failures must change strategy; external-authority blockers pause for minimal owner "
                "action; exhausted jobs are quarantined."
            ),
        }
        self.todo_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return payload

    def assign_next(self) -> dict:
        authority = issue_authority_enabled(self.root)
        issue_sync = route_unbacked_tasks(self.root)
        self.write_todo()
        active = self.active()
        if len(active) >= ACTIVE_TASK_LIMIT:
            result = {
                "status": "active_slots_full",
                "decision": None,
                "active": len(active),
                "active_limit": ACTIVE_TASK_LIMIT,
                "active_task_ids": [task.task_id for task in active],
                "github_issue_authority_enforced": authority,
                "github_issue_sync": issue_sync,
            }
            self.last_route_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            return result

        pending = self.pending()
        candidates = [
            task for task in pending
            if (not authority or issue_backed(task))
            and (task.state == "new" or self.queue.retryable(task))
        ]
        if not candidates:
            unbacked = [task.task_id for task in pending if authority and not issue_backed(task)]
            result = {
                "status": "waiting_for_github_issue" if unbacked else "idle",
                "decision": None,
                "active": len(active),
                "active_limit": ACTIVE_TASK_LIMIT,
                "unbacked_task_ids": unbacked,
                "github_issue_authority_enforced": authority,
                "github_issue_sync": issue_sync,
            }
            self.last_route_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            return result

        task = candidates[0]
        decision = self.route(task)
        recovery = JobFailureIntelligence.plan(task) if task.state == "failed" else None
        problem_step = None

        if task.state == "failed":
            evidence = [str(row.get("error", "")) for row in task.failure_history[-3:]]
            problem_step = self.problem_solver.solve_step(task, evidence=evidence)
            diagnosis = problem_step["diagnosis"]
            if diagnosis["owner_action_required"]:
                paused = self.queue.pause(
                    task.task_id,
                    f"External authority required: {diagnosis['root_cause']} Next action: {diagnosis['repair_strategy']}",
                )
                result = {
                    "status": "blocked_external_authority",
                    "decision": None,
                    "task": asdict(paused),
                    "active": len(active),
                    "active_limit": ACTIVE_TASK_LIMIT,
                    "problem_solver": problem_step,
                    "recovery_plan": recovery.as_dict() if recovery else None,
                    "github_issue_authority_enforced": authority,
                    "github_issue_sync": issue_sync,
                }
                self.last_route_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
                self.write_todo()
                return result

            decision = RouteDecision(
                task.task_id,
                diagnosis["next_module"],
                True if diagnosis["classification"] != "transient" else decision.use_ai_team,
                (
                    f"autonomous problem solver diagnosed {diagnosis['classification']}; "
                    f"strategy={diagnosis['repair_strategy']}"
                ),
            )

        if authority and not issue_backed(task):
            raise RuntimeError("GitHub Issue is required before task assignment")

        assigned = self.queue.transition(task.task_id, "assigned", module_id=decision.module_id)
        result = {
            "status": "assigned",
            "decision": decision.as_dict(),
            "task": asdict(assigned),
            "active": len(active) + 1,
            "active_limit": ACTIVE_TASK_LIMIT,
            "ai_team_module": "genesis.ai_team" if decision.use_ai_team else None,
            "recovery_plan": recovery.as_dict() if recovery else None,
            "problem_solver": problem_step,
            "github_issue_authority_enforced": authority,
            "github_issue_sync": issue_sync,
        }
        self.last_route_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        self.write_todo()
        return result
