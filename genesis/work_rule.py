from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .gene_names import identity_for_logical_id
from .modules.task_queue import GenesisTask, PersistentTaskQueue


UNRESOLVED_STATES = {"new", "assigned", "running", "blocked", "review", "failed", "quarantined"}


@dataclass(frozen=True)
class WorkDecision:
    gene: str
    logical_id: str
    mode: str
    task_id: str | None
    objective: str | None
    reason: str


class GeneWorkRule:
    """Persistent one-issue-at-a-time work policy for a Gene.

    The rule preserves issue focus across retries and restarts. A failed task does
    not cause topic switching. If no unresolved work exists, the Gene enters
    learn/discover mode and should immediately reassess after creating evidence or
    identifying a real issue. Timer schedules may wake a runtime but are never the
    authority that decides whether work continues.
    """

    def __init__(self, root: Path, logical_id: str, queue: PersistentTaskQueue | None = None) -> None:
        self.root = Path(root).resolve()
        self.logical_id = logical_id
        self.identity = identity_for_logical_id(logical_id)
        self.queue = queue or PersistentTaskQueue(self.root / "runtime" / "genesis_tasks.sqlite3")
        self.state_path = self.root / "runtime" / "grce" / logical_id / "work_focus.json"
        self.state_path.parent.mkdir(parents=True, exist_ok=True)

    def _load_focus(self) -> dict[str, Any] | None:
        if not self.state_path.exists():
            return None
        try:
            payload = json.loads(self.state_path.read_text(encoding="utf-8"))
        except Exception:
            return None
        return payload if isinstance(payload, dict) else None

    def _save_focus(self, task: GenesisTask) -> None:
        payload = {
            "gene": self.identity.display_name,
            "logical_id": self.logical_id,
            "task_id": task.task_id,
            "objective": task.objective,
            "rule": "keep_focus_until_resolved_or_genuinely_external_blocked",
        }
        self.state_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    def clear_focus(self) -> None:
        if self.state_path.exists():
            self.state_path.unlink()

    @staticmethod
    def _is_genuinely_external_block(task: GenesisTask) -> bool:
        payload = dict(task.payload or {})
        return bool(payload.get("external_blocked")) and bool(payload.get("external_dependency"))

    def _focused_task(self) -> GenesisTask | None:
        focus = self._load_focus()
        if not focus:
            return None
        task_id = str(focus.get("task_id") or "")
        task = self.queue.get(task_id) if task_id else None
        if task is None or task.state == "complete":
            self.clear_focus()
            return None
        if self._is_genuinely_external_block(task):
            self.clear_focus()
            return None
        return task

    def _next_unresolved(self) -> GenesisTask | None:
        candidates: list[GenesisTask] = []
        for state in UNRESOLVED_STATES:
            candidates.extend(self.queue.list(state=state, limit=500))
        candidates = [task for task in candidates if not self._is_genuinely_external_block(task)]
        if not candidates:
            return None
        candidates.sort(key=lambda task: (-task.priority, task.created_at, task.task_id))
        return candidates[0]

    def decide(self) -> WorkDecision:
        task = self._focused_task()
        if task is not None:
            return WorkDecision(
                gene=self.identity.display_name,
                logical_id=self.logical_id,
                mode="solve_issue",
                task_id=task.task_id,
                objective=task.objective,
                reason="persistent_focus_existing_issue",
            )

        task = self._next_unresolved()
        if task is not None:
            self._save_focus(task)
            return WorkDecision(
                gene=self.identity.display_name,
                logical_id=self.logical_id,
                mode="solve_issue",
                task_id=task.task_id,
                objective=task.objective,
                reason="selected_highest_priority_unresolved_issue",
            )

        return WorkDecision(
            gene=self.identity.display_name,
            logical_id=self.logical_id,
            mode="learn_discover",
            task_id=None,
            objective=None,
            reason="no_unresolved_issue_found",
        )

    def status(self) -> dict[str, Any]:
        decision = self.decide()
        return {
            **asdict(decision),
            "max_active_issues": 1,
            "failure_releases_focus": False,
            "timer_required": False,
            "idle_sequence": [
                "learn",
                "search_for_evidence_or_unsolved_problems",
                "review_deferred_issues",
                "inspect_capability_gaps",
                "experiment",
                "reassess",
            ],
        }
