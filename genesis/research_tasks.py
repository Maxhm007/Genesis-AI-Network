from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from .github_issue_task_router import issue_authority_enabled, issue_backed, route_unbacked_tasks
from .github_issue_terminal_reconciler import reconcile_terminal_github_issues
from .modules.task_queue import PersistentTaskQueue
from .providers import ProviderRegistry
from .specialist_issue_completion import publish_specialist_completion_evidence
from .team import AITeam


SUPPORTED_TASK_TYPES = {
    "immortality_research",
    "competitive_ai_improvement",
    "competitive_reference_refresh",
}


class ImmortalityResearchWorker:
    """Advance one high-priority Genesis mission task to a preserved review artifact.

    GitHub Issues are authoritative in the real Genesis runtime. Research work may
    be discovered internally, but it cannot run there until it has an Issue.
    Completion means the requested review artifact was produced; it does not promote
    scientific claims or benchmark values.
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

    @staticmethod
    def _issue_closed(issue_number: int, reconciliation: dict) -> bool:
        if issue_number <= 0:
            return False
        if issue_number in (reconciliation.get("already_closed") or []):
            return True
        return any(
            int(item.get("github_issue_number") or 0) == issue_number
            for item in (reconciliation.get("closed") or [])
            if isinstance(item, dict)
        )

    def _review_path(self, task_id: str) -> Path:
        return self.root / "runtime" / "task_reviews" / f"{task_id}.json"

    @staticmethod
    def _team_members_from_review(review_path: Path) -> list[str]:
        try:
            review = json.loads(review_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []
        outputs = review.get("team_outputs") if isinstance(review, dict) else []
        if not isinstance(outputs, list):
            return []
        return [
            str(item.get("agent") or "")
            for item in outputs
            if isinstance(item, dict) and str(item.get("agent") or "").strip()
        ]

    def _finish_review_reconciliation(self, task, *, issue_sync: dict) -> dict:
        """Retry GitHub evidence/closure for an existing review without rerunning AI work."""
        task_type = str(task.payload.get("task_type"))
        module_id = "genesis.research" if task_type == "immortality_research" else "genesis.capability"
        issue_number = int(task.payload.get("github_issue_number") or 0)
        review_path = self._review_path(task.task_id)
        team_members = self._team_members_from_review(review_path)
        evidence_result = publish_specialist_completion_evidence(
            self.root,
            task,
            review_path=review_path,
            team_members=team_members,
        )
        if not evidence_result.get("reported"):
            return {
                "status": "github_issue_reconciliation_pending",
                "reason": evidence_result.get("reason") or evidence_result.get("status"),
                "task_id": task.task_id,
                "task_type": task_type,
                "priority": task.priority,
                "state": task.state,
                "github_issue_number": issue_number,
                "review_artifact": str(review_path.relative_to(self.root)),
                "team_members": team_members,
                "github_issue_authority_enforced": True,
                "github_issue_sync": issue_sync,
                "github_completion_evidence": evidence_result,
                "github_issue_reconciled": False,
                "research_reexecuted": False,
            }

        updated = self.queue.transition(task.task_id, "complete", module_id=module_id)
        terminal_reconciliation = reconcile_terminal_github_issues(self.root)
        issue_reconciled = self._issue_closed(issue_number, terminal_reconciliation)
        return {
            "status": "review_completed" if issue_reconciled else "github_issue_close_pending",
            "task_id": task.task_id,
            "task_type": task_type,
            "priority": task.priority,
            "state": updated.state,
            "github_issue_number": issue_number,
            "review_artifact": str(review_path.relative_to(self.root)),
            "team_members": team_members,
            "github_issue_authority_enforced": True,
            "github_issue_sync": issue_sync,
            "github_completion_evidence": evidence_result,
            "github_terminal_reconciliation": terminal_reconciliation,
            "github_issue_reconciled": issue_reconciled,
            "research_reexecuted": False,
        }

    def run_one(self) -> dict:
        authority = issue_authority_enabled(self.root)
        issue_sync = route_unbacked_tasks(self.root)
        tasks = self.queue.list(limit=200)

        # If a previous cycle completed the internal task but GitHub closure failed,
        # retry only the terminal reconciliation. Never rerun specialist research.
        if authority:
            completed_issue_tasks = [
                task for task in tasks
                if issue_backed(task)
                and task.state == "complete"
                and task.payload.get("task_type") in SUPPORTED_TASK_TYPES
            ]
            if completed_issue_tasks:
                task = completed_issue_tasks[0]
                issue_number = int(task.payload.get("github_issue_number") or 0)
                terminal_reconciliation = reconcile_terminal_github_issues(self.root)
                issue_reconciled = self._issue_closed(issue_number, terminal_reconciliation)
                return {
                    "status": "review_completed" if issue_reconciled else "github_issue_close_pending",
                    "task_id": task.task_id,
                    "task_type": str(task.payload.get("task_type")),
                    "priority": task.priority,
                    "state": task.state,
                    "github_issue_number": issue_number,
                    "github_issue_authority_enforced": True,
                    "github_issue_sync": issue_sync,
                    "github_terminal_reconciliation": terminal_reconciliation,
                    "github_issue_reconciled": issue_reconciled,
                    "research_reexecuted": False,
                }

            review_issue_tasks = [
                task for task in tasks
                if issue_backed(task)
                and task.state == "review"
                and task.payload.get("task_type") in SUPPORTED_TASK_TYPES
            ]
            if review_issue_tasks:
                return self._finish_review_reconciliation(review_issue_tasks[0], issue_sync=issue_sync)

        candidates = [
            task for task in tasks
            if (not authority or issue_backed(task))
            and task.state in {"new", "assigned"}
            and task.payload.get("task_type") in SUPPORTED_TASK_TYPES
        ]
        if not candidates:
            unbacked = [
                task.task_id for task in tasks
                if authority
                and not issue_backed(task)
                and task.state in {"new", "assigned"}
                and task.payload.get("task_type") in SUPPORTED_TASK_TYPES
            ]
            return {
                "status": "waiting_for_github_issue" if unbacked else "idle",
                "reason": "no_issue_backed_supported_runnable_task" if authority else "no_supported_runnable_task",
                "unbacked_task_ids": unbacked,
                "github_issue_authority_enforced": authority,
                "github_issue_sync": issue_sync,
            }
        task = candidates[0]
        if authority and not issue_backed(task):
            raise RuntimeError("GitHub Issue is required before autonomous research execution")
        task_type = str(task.payload.get("task_type"))
        module_id = "genesis.research" if task_type == "immortality_research" else "genesis.capability"
        if task.state == "new":
            self.queue.transition(task.task_id, "assigned", module_id=module_id)
        self.queue.transition(task.task_id, "running", module_id=module_id)
        outputs = self.team.run_task(task.objective, context=self._context(task))
        issue_number = int(task.payload.get("github_issue_number") or 0)
        review = {
            "task": asdict(task),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "status": "candidate_review",
            "team_outputs": outputs,
            "github_issue_number": issue_number,
            "rule": "Candidate evidence only. Completion of this work item does not promote evidence, benchmark claims, knowledge, scores, or protected code.",
        }
        out_dir = self.root / "runtime" / "task_reviews"
        out_dir.mkdir(parents=True, exist_ok=True)
        review_path = out_dir / f"{task.task_id}.json"
        review_path.write_text(json.dumps(review, indent=2) + "\n", encoding="utf-8")
        review_task = self.queue.transition(task.task_id, "review", module_id=module_id)
        team_members = [str(item.get("agent") or "") for item in outputs]

        evidence_result = None
        if authority and issue_number > 0:
            evidence_result = publish_specialist_completion_evidence(
                self.root,
                review_task,
                review_path=review_path,
                team_members=team_members,
            )
            if not evidence_result.get("reported"):
                return {
                    "status": "github_issue_reconciliation_pending",
                    "reason": evidence_result.get("reason") or evidence_result.get("status"),
                    "task_id": task.task_id,
                    "task_type": task_type,
                    "priority": task.priority,
                    "state": review_task.state,
                    "github_issue_number": issue_number,
                    "review_artifact": str(review_path.relative_to(self.root)),
                    "team_members": team_members,
                    "github_issue_authority_enforced": authority,
                    "github_issue_sync": issue_sync,
                    "github_completion_evidence": evidence_result,
                    "github_issue_reconciled": False,
                    "research_reexecuted": True,
                }

        updated = self.queue.transition(task.task_id, "complete", module_id=module_id)
        terminal_reconciliation = None
        issue_reconciled = False
        if authority and issue_number > 0:
            terminal_reconciliation = reconcile_terminal_github_issues(self.root)
            issue_reconciled = self._issue_closed(issue_number, terminal_reconciliation)

        return {
            "status": "review_completed" if not authority or issue_number <= 0 or issue_reconciled else "github_issue_close_pending",
            "task_id": task.task_id,
            "task_type": task_type,
            "priority": task.priority,
            "state": updated.state,
            "github_issue_number": issue_number,
            "review_artifact": str(review_path.relative_to(self.root)),
            "team_members": team_members,
            "github_issue_authority_enforced": authority,
            "github_issue_sync": issue_sync,
            "github_completion_evidence": evidence_result,
            "github_terminal_reconciliation": terminal_reconciliation,
            "github_issue_reconciled": issue_reconciled,
            "research_reexecuted": True,
        }
