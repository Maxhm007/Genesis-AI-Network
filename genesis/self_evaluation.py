from __future__ import annotations

from pathlib import Path

from .autonomy_proof import AutonomyProofLedger
from .modules.task_queue import PersistentTaskQueue


SELF_DEVELOPMENT_MODULES = {
    "genesis.coding",
    "genesis.self_development",
    "genesis.ai_score",
    "genesis.application",
    "genesis.model_scout",
    "genesis.blockchain",
    "genesis.updater",
    "genesis.security",
    "genesis.automation",
    "genesis.evaluation",
}

OWNER_ACTORS = {"owner", "user", "human"}
ASSISTED_ACTORS = {"chatgpt", "assistant", "external", "unknown"}


class GenesisSelfEvaluation:
    """Machine-readable development history with explicit attribution.

    Genesis must be able to distinguish its own successful development from
    owner-initiated and assisted engineering. Generic completed engineering is
    still retained as advisory memory, but it never receives autonomous credit
    without an Autonomy Proof cycle classified ``genesis_autonomous``.
    """

    def __init__(self, root: Path) -> None:
        self.root = Path(root).resolve()
        self.runtime = self.root / "runtime"
        self.queue = PersistentTaskQueue(self.runtime / "genesis_tasks.sqlite3")
        self.proof = AutonomyProofLedger(self.root)

    def _completed_engineering_tasks(self, limit: int = 100) -> list[dict]:
        tasks = [
            task
            for task in self.queue.list(state="complete", limit=max(1, limit))
            if task.module_id in SELF_DEVELOPMENT_MODULES
            or task.payload.get("task_type") in {"coding", "self_development", "benchmark_runner", "capability_growth"}
        ]
        tasks.sort(key=lambda task: (task.updated_at, task.task_id), reverse=True)
        return [
            {
                "task_id": task.task_id,
                "module": task.module_id,
                "improved": task.objective,
                "completed_at": task.updated_at,
                "attempts": task.attempt_count,
                "source": task.payload.get("source"),
                "task_type": task.payload.get("task_type"),
                "credit": "engineering_memory_only",
            }
            for task in tasks[:limit]
        ]

    def _completed_cycles(self) -> list[dict]:
        events = self.proof.events(limit=5000)
        by_cycle: dict[str, list[dict]] = {}
        for event in events:
            by_cycle.setdefault(str(event.get("cycle_id", "")), []).append(event)

        rows: list[dict] = []
        for cycle_id, cycle in by_cycle.items():
            completed = next(
                (
                    event
                    for event in reversed(cycle)
                    if event.get("stage") == "cycle_complete" and event.get("outcome") == "success"
                ),
                None,
            )
            if completed is None:
                continue
            discovery = next((event for event in cycle if event.get("stage") == "discovery"), {})
            candidate = next((event for event in reversed(cycle) if event.get("stage") == "candidate_created"), {})
            detail = discovery.get("details") or {}
            candidate_detail = candidate.get("details") or {}
            actor = str(completed.get("actor") or "unknown").strip().lower()
            classification = str(completed.get("classification") or "external")
            if classification == "genesis_autonomous":
                attribution = "genesis_autonomous"
            elif actor in OWNER_ACTORS:
                attribution = "owner"
            else:
                attribution = "assisted"
            rows.append(
                {
                    "cycle_id": cycle_id,
                    "improved": detail.get("title") or "Bounded Genesis development",
                    "files": detail.get("files") or [],
                    "branch": candidate_detail.get("branch"),
                    "commit_sha": candidate_detail.get("commit_sha"),
                    "completed_at": completed.get("recorded_at"),
                    "actor": completed.get("actor"),
                    "classification": classification,
                    "attribution": attribution,
                    "credit": "self_development" if attribution == "genesis_autonomous" else "engineering_memory_only",
                }
            )
        rows.sort(key=lambda item: str(item.get("completed_at") or ""), reverse=True)
        return rows

    def report(self, limit: int = 20) -> dict:
        engineering = self._completed_engineering_tasks(limit=1000)
        cycles = self._completed_cycles()
        autonomous = [row for row in cycles if row["attribution"] == "genesis_autonomous"]
        assisted = [row for row in cycles if row["attribution"] == "assisted"]
        owner = [row for row in cycles if row["attribution"] == "owner"]
        proof = self.proof.report(limit=1000)
        return {
            "completed_self_development_tasks": len(autonomous),
            "development_attribution": {
                "genesis_autonomous": len(autonomous),
                "assisted": len(assisted),
                "owner": len(owner),
                "total_proven_cycles": len(cycles),
            },
            "recent_completed_tasks": engineering[:limit],
            "recent_autonomous_improvements": autonomous[:limit],
            "recent_assisted_improvements": assisted[:limit],
            "recent_owner_improvements": owner[:limit],
            "recent_attributed_development": cycles[:limit],
            "completed_engineering_tasks_observed": len(engineering),
            "autonomy_proof": proof,
            "interpretation": (
                "Genesis Autonomous means Genesis initiated/completed a successful proven cycle. "
                "Assisted means an external assistant or unowned external actor drove the cycle. "
                "Owner means the owner/user/human drove the cycle. Completed engineering is retained as advisory memory."
            ),
            "rule": (
                "Owner and assisted work must never increase Genesis autonomous self-development credit. "
                "Every proven completed cycle belongs to exactly one attribution bucket."
            ),
        }
