from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from .modules.task_queue import PersistentTaskQueue
from .providers import ProviderRegistry
from .team import AITeam


class ImmortalityResearchWorker:
    """Advance one persistent immortality research task to human/validator review.

    Generated analysis remains candidate evidence. This worker cannot promote
    scientific claims into validated knowledge and cannot modify protected identity.
    """

    def __init__(self, root: Path, providers: ProviderRegistry | None = None) -> None:
        self.root = root.resolve()
        self.providers = providers or ProviderRegistry()
        self.team = AITeam(self.providers)
        self.queue = PersistentTaskQueue(self.root / "runtime" / "genesis_tasks.sqlite3")

    def run_one(self) -> dict:
        candidates = [
            task for task in self.queue.list(state="new", limit=100)
            if task.payload.get("task_type") == "immortality_research"
        ]
        if not candidates:
            return {"status": "idle", "reason": "no_new_immortality_research_task"}
        task = candidates[0]
        self.queue.transition(task.task_id, "assigned", module_id="genesis.research")
        self.queue.transition(task.task_id, "running")
        context = (
            "Treat the source as candidate evidence only. Examine whether the proposed pathway to continuous physical human immortality is defensible, "
            "what evidence is missing, possible confounders or harms, and the smallest next research action. Do not invent findings. "
            f"SOURCE={task.payload.get('source')} URL={task.payload.get('url')} PUBLISHED={task.payload.get('published')} "
            f"RELEVANCE={task.payload.get('relevance')} PATHWAY={task.payload.get('pathway_hypothesis')}"
        )
        outputs = self.team.run_task(task.objective, context=context)
        review = {
            "task": asdict(task),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "status": "candidate_review",
            "team_outputs": outputs,
            "rule": "This review is not validated scientific knowledge. It requires evidence verification before promotion.",
        }
        out_dir = self.root / "runtime" / "research_reviews"
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / f"{task.task_id}.json").write_text(json.dumps(review, indent=2) + "\n", encoding="utf-8")
        updated = self.queue.transition(task.task_id, "review")
        return {"status": "review_ready", "task_id": task.task_id, "priority": task.priority, "state": updated.state, "team_members": [item.get("agent") for item in outputs]}
