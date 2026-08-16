from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from .modules.task_queue import PersistentTaskQueue
from .providers import ProviderRegistry
from .team import AITeam


SUPPORTED_TASK_TYPES = {
    "immortality_research",
    "competitive_ai_improvement",
    "competitive_reference_refresh",
}


class ImmortalityResearchWorker:
    """Advance one high-priority Genesis mission task to candidate review.

    Despite the historical class name, this worker handles immortality research
    and competitive-AI maintenance tasks. Outputs remain candidate evidence and
    cannot promote scientific claims, benchmark targets, or protected code.
    """

    def __init__(self, root: Path, providers: ProviderRegistry | None = None) -> None:
        self.root = root.resolve()
        self.providers = providers or ProviderRegistry()
        self.team = AITeam(self.providers, max_roles_per_task=3)
        self.queue = PersistentTaskQueue(self.root / "runtime" / "genesis_tasks.sqlite3")

    @staticmethod
    def _context(task) -> str:
        task_type = task.payload.get("task_type")
        if task_type == "immortality_research":
            return (
                "Treat the source as candidate evidence only. Examine whether the proposed pathway to continuous physical human immortality is defensible, "
                "what evidence is missing, possible confounders or harms, and the smallest next research action. Do not invent findings. "
                f"SOURCE={task.payload.get('source')} URL={task.payload.get('url')} PUBLISHED={task.payload.get('published')} "
                f"RELEVANCE={task.payload.get('relevance')} PATHWAY={task.payload.get('pathway_hypothesis')}"
            )
        if task_type == "competitive_ai_improvement":
            return (
                "Genesis is below its moving competitive AI reference. Diagnose the named dimension. Prefer measurable benchmark work, replaceable provider scouting, "
                "or a small bounded system improvement. Do not self-award benchmark points and do not claim unmeasured capability. "
                f"CURRENT_SCORE={task.payload.get('competitive_score')} REFERENCE_AS_OF={task.payload.get('reference_as_of')} DIMENSION={task.payload.get('dimension')}"
            )
        return (
            "Review current official frontier AI evaluation disclosures and identify whether the configured Genesis competitive reference needs a provenance-backed update. "
            "Do not rewrite benchmark values from unverified text; record exact source, metric, evaluation conditions and uncertainty. "
            f"CURRENT_REFERENCE={task.payload.get('current_reference_as_of')} SOURCES={task.payload.get('sources')}"
        )

    def run_one(self) -> dict:
        candidates = [
            task for task in self.queue.list(state="new", limit=100)
            if task.payload.get("task_type") in SUPPORTED_TASK_TYPES
        ]
        if not candidates:
            return {"status": "idle", "reason": "no_supported_new_task"}
        task = candidates[0]
        task_type = str(task.payload.get("task_type"))
        module_id = "genesis.research" if task_type == "immortality_research" else "genesis.capability"
        self.queue.transition(task.task_id, "assigned", module_id=module_id)
        self.queue.transition(task.task_id, "running")
        outputs = self.team.run_task(task.objective, context=self._context(task))
        review = {
            "task": asdict(task),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "status": "candidate_review",
            "team_outputs": outputs,
            "rule": "Candidate review only. Evidence/benchmark claims require verification before knowledge, reference, score, or code promotion.",
        }
        out_dir = self.root / "runtime" / "task_reviews"
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / f"{task.task_id}.json").write_text(json.dumps(review, indent=2) + "\n", encoding="utf-8")
        updated = self.queue.transition(task.task_id, "review")
        return {
            "status": "review_ready",
            "task_id": task.task_id,
            "task_type": task_type,
            "priority": task.priority,
            "state": updated.state,
            "team_members": [item.get("agent") for item in outputs],
        }
