from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
from pathlib import Path

from .modules.task_queue import PersistentTaskQueue


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class AutomationDecision:
    issue_key: str
    title: str
    action: str
    attempts: int
    task_id: str | None
    task_state: str | None
    reason: str

    def as_dict(self) -> dict:
        return asdict(self)


class GenesisAutomationModule:
    """Coordinate bounded autonomous repair and escalation.

    Genesis gets a limited number of autonomous repair cycles. Persistent
    unresolved issues are escalated for external assistance, but escalation
    never grants authority to bypass Constitution, Security, validation,
    protected-file, signing, credential, or owner-control boundaries.
    """

    def __init__(self, root: Path, max_autonomous_attempts: int = 2) -> None:
        self.root = Path(root).resolve()
        self.runtime = self.root / "runtime"
        self.runtime.mkdir(parents=True, exist_ok=True)
        self.queue = PersistentTaskQueue(self.runtime / "genesis_tasks.sqlite3")
        self.state_path = self.runtime / "automation_state.json"
        self.max_autonomous_attempts = max(1, int(max_autonomous_attempts))

    def _load_state(self) -> dict:
        try:
            return json.loads(self.state_path.read_text(encoding="utf-8"))
        except Exception:
            return {"issues": {}}

    def _task_for_issue(self, issue_key: str):
        for task in self.queue.list(limit=5000):
            if task.payload.get("issue_key") == issue_key and task.payload.get("task_type") == "operational_issue":
                return task
        return None

    def evaluate(self, operations_report: dict) -> dict:
        state = self._load_state()
        issue_state = dict(state.get("issues", {}))
        now = utc_now()
        decisions: list[AutomationDecision] = []
        active_keys: set[str] = set()

        for issue in operations_report.get("issues", []):
            key = str(issue.get("issue_key", "")).strip()
            if not key:
                continue
            status = str(issue.get("status", "open"))
            if status == "resolved":
                prior = dict(issue_state.get(key, {}))
                prior.update({"status": "resolved", "resolved_at": issue.get("resolved_at", now), "last_seen_at": now})
                issue_state[key] = prior
                decisions.append(AutomationDecision(key, str(issue.get("title", key)), "resolved", int(prior.get("attempts", 0)), None, None, "Issue is no longer detected."))
                continue

            active_keys.add(key)
            prior = dict(issue_state.get(key, {}))
            attempts = int(prior.get("attempts", 0)) + 1
            task = self._task_for_issue(key)
            task_state = task.state if task is not None else None
            task_id = task.task_id if task is not None else None
            owner_only = bool(issue.get("owner_action_required", False))

            if owner_only:
                action = "owner_action"
                reason = "Issue requires an owner-controlled secret, credential, policy choice, signing key, or other non-delegable action."
            elif task_state in {"failed", "blocked"}:
                action = "escalate_chatgpt"
                reason = f"Genesis repair task is {task_state}; external engineering assistance is requested without weakening safeguards."
            elif attempts > self.max_autonomous_attempts:
                action = "escalate_chatgpt"
                reason = f"Issue remained unresolved after {self.max_autonomous_attempts} bounded autonomous repair cycles."
            else:
                action = "retry_autonomous"
                reason = f"Genesis retains autonomous repair authority for attempt {attempts}/{self.max_autonomous_attempts}."

            prior.update({
                "title": issue.get("title"),
                "status": status,
                "attempts": attempts,
                "task_id": task_id,
                "task_state": task_state,
                "action": action,
                "last_seen_at": now,
            })
            if action == "escalate_chatgpt" and not prior.get("escalated_at"):
                prior['escalated_at'] = now
            issue_state[key] = prior
            decisions.append(AutomationDecision(key, str(issue.get("title", key)), action, attempts, task_id, task_state, reason))

        state = {"updated_at": now, "max_autonomous_attempts": self.max_autonomous_attempts, "issues": issue_state}
        self.state_path.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        report = {
            "updated_at": now,
            "decisions": [item.as_dict() for item in decisions],
            "retry": sum(1 for item in decisions if item.action == "retry_autonomous"),
            "escalate_chatgpt": sum(1 for item in decisions if item.action == "escalate_chatgpt"),
            "owner_action": sum(1 for item in decisions if item.action == "owner_action"),
            "resolved": sum(1 for item in decisions if item.action == "resolved"),
        }
        (self.runtime / "automation_report.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return report
