from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from .github_issue_task_router import issue_backed, route_unbacked_tasks
from .modules.task_queue import PersistentTaskQueue
from .providers import ProviderRegistry
from .team import AITeam


SUPPORTED_TASK_TYPES = {
    "immortality_research",
    "competitive_ai_improvement",
    "competitive_reference_refresh",
}


class ImmortalityResearchWorker:
    """Advance one high-priority Genesis mission task to a preserved review artifact.

    GitHub Issues are authoritative. Research work may be discovered internally, but
    it cannot run until it has an Issue. Completion means the requested review
    artifact was produced; it does not promote scientific claims or benchmark values.
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
        issue_sync = route_unbacked_tasks(self.root)
        candidates = [
            task for task in self.queue.list(limit=200)
            if issue_backed(task)
            and task.state in {"new", "assigned"}
            and task.payload.get("task_type") in SUPPORTED_TASK_TYPES
        ]
        if not candidates:
            unbacked = [
                task.task_id for task in self.queue.list(limit=200)
                if not issue_backed(task)
                and task.state in {"new", "assigned"}
                and task.payload.get("task_type") in SUPPORTED_TASK_TYPES
            ]
            return {
                "status": "waiting_for_github_issue" if unbacked else "idle",
                "reason": "no_issue_backed_supported_runnable_task",
                "unbacked_task_ids": unbacked,
                "github_issue_sync": issue_sync,
            }
        task = candidates[0]
        task_type = str(task.payload.get("task_type"))
        module_id = "genesis.research" if task_type == "immortality_research" else "genesis.capability"
        if task.state == "new":
            self.queue.transition(task.task_id, "assigned", module_id=module_id)
        self.queue.transition(task.task_id, "running", module_id=module_id)
        outputs = self.team.run_task(task.objective, context=self._context(task))
        review = {
            "task": asdict(task),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "status": "candidate_review",
            "team_outputs": outputs,
            "github_issue_number": int(task.payload.get("github_issue_number") or 0),
            "rule": "Candidate evidence only. Completion of this work item does not promote evidence, benchmark claims, knowledge, scores, or protected code.",
        }
        out_dir = self.root / "runtime" / "task_reviews"
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / f"{task.task_id}.json").write_text(json.dumps(review, indent=2) + "\n", encoding="utf-8")
        self.queue.transition(task.task_id, "review", module_id=module_id)
        updated = self.queue.transition(task.task_id, "complete", module_id=module_id)
        return {
            "status": "review_completed",
            "task_id": task.task_id,
            "task_type": task_type,
            "priority": task.priority,
            "state": updated.state,
            "github_issue_number": int(task.payload.get("github_issue_number") or 0),
            "team_members": [item.get("agent") for item in outputs],
            "github_issue_sync": issue_sync,
        }
