from __future__ import annotations

from dataclasses import asdict
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


class GenesisSelfEvaluation:
    """Machine-readable history of what Genesis has actually improved.

    Runtime task completions are the source of truth for completed work. The
    autonomy proof ledger supplies provenance/candidate evidence. This report is
    deliberately descriptive and does not award capability score by itself.
    """

    def __init__(self, root: Path) -> None:
        self.root = Path(root).resolve()
        self.runtime = self.root / "runtime"
        self.queue = PersistentTaskQueue(self.runtime / "genesis_tasks.sqlite3")
        self.proof = AutonomyProofLedger(self.root)

    def _completed_tasks(self, limit: int = 100) -> list[dict]:
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
            }
            for task in tasks[:limit]
        ]

    def _autonomous_improvements(self, limit: int = 20) -> list[dict]:
        events = self.proof.events(limit=1000)
        by_cycle: dict[str, list[dict]] = {}
        for event in events:
            by_cycle.setdefault(str(event.get("cycle_id", "")), []).append(event)

        improvements: list[dict] = []
        for cycle_id, cycle in by_cycle.items():
            completed = next(
                (
                    event
                    for event in reversed(cycle)
                    if event.get("stage") == "cycle_complete"
                    and event.get("outcome") == "success"
                    and event.get("classification") == "genesis_autonomous"
                ),
                None,
            )
            if completed is None:
                continue
            discovery = next((event for event in cycle if event.get("stage") == "discovery"), {})
            candidate = next((event for event in reversed(cycle) if event.get("stage") == "candidate_created"), {})
            detail = discovery.get("details") or {}
            candidate_detail = candidate.get("details") or {}
            improvements.append(
                {
                    "cycle_id": cycle_id,
                    "improved": detail.get("title") or "Bounded Genesis self-development",
                    "files": detail.get("files") or [],
                    "branch": candidate_detail.get("branch"),
                    "commit_sha": candidate_detail.get("commit_sha"),
                    "completed_at": completed.get("recorded_at"),
                    "classification": "genesis_autonomous",
                }
            )
        improvements.sort(key=lambda item: str(item.get("completed_at") or ""), reverse=True)
        return improvements[:limit]

    def report(self, limit: int = 20) -> dict:
        completed = self._completed_tasks(limit=1000)
        autonomous = self._autonomous_improvements(limit=limit)
        proof = self.proof.report(limit=1000)
        return {
            "completed_self_development_tasks": len(completed),
            "recent_completed_tasks": completed[:limit],
            "recent_autonomous_improvements": autonomous,
            "autonomy_proof": proof,
            "interpretation": (
                "Completed task count comes from persistent tasks in complete state. "
                "Autonomous improvement details come from Genesis's provenance ledger."
            ),
            "rule": "Self-development evidence is descriptive; it cannot self-award benchmark or capability credit.",
        }
