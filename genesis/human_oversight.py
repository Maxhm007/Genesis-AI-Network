from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .issue_opening_manager import build_agentic_candidate


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _goal_id(title: str, objective: str) -> str:
    digest = hashlib.sha256(f"{title.strip()}\0{objective.strip()}".encode("utf-8")).hexdigest()[:16]
    return f"owner-goal:{digest}"


class HumanOversight:
    """Goal-driven, evidence-first governance surface for Genesis.

    Humans define goals, priorities and protected boundaries. Genesis turns those
    goals into traceable autonomous work, while ordinary in-boundary execution
    stays autonomous. Only owner-authority or genuinely ambiguous decisions are
    surfaced for human action.
    """

    VERSION = 1

    def __init__(self, root: Path) -> None:
        self.root = Path(root).resolve()
        self.path = self.root / "runtime" / "human_oversight.json"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.state = self._load()

    def _default(self) -> dict[str, Any]:
        return {"version": self.VERSION, "goals": {}, "updated_at": _utc_now()}

    def _load(self) -> dict[str, Any]:
        if not self.path.is_file():
            return self._default()
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return self._default()
        if not isinstance(payload, dict):
            return self._default()
        payload.setdefault("goals", {})
        payload["version"] = self.VERSION
        return payload

    def _save(self) -> None:
        self.state["updated_at"] = _utc_now()
        self.path.write_text(json.dumps(self.state, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    def define_goal(
        self,
        *,
        title: str,
        objective: str,
        priority: int = 50,
        success_criteria: list[str] | None = None,
        protected_boundaries: list[str] | None = None,
    ) -> dict[str, Any]:
        title = str(title or "").strip()
        objective = str(objective or "").strip()
        if not title or not objective:
            raise ValueError("title and objective are required")
        goal_id = _goal_id(title, objective)
        now = _utc_now()
        goal = self.state["goals"].get(goal_id)
        if goal is None:
            goal = {
                "goal_id": goal_id,
                "title": title,
                "objective": objective,
                "priority": max(0, min(100, int(priority))),
                "success_criteria": [str(x).strip() for x in success_criteria or [] if str(x).strip()],
                "protected_boundaries": [str(x).strip() for x in protected_boundaries or [] if str(x).strip()],
                "status": "approved",
                "created_at": now,
                "updated_at": now,
                "priority_history": [],
                "issue_numbers": [],
                "evidence": [],
                "escalations": [],
            }
            self.state["goals"][goal_id] = goal
        self._save()
        return dict(goal)

    def change_priority(self, goal_id: str, priority: int, *, reason: str) -> dict[str, Any]:
        goal = self.state["goals"].get(goal_id)
        if not goal:
            raise KeyError(goal_id)
        previous = int(goal.get("priority", 50))
        current = max(0, min(100, int(priority)))
        goal["priority_history"].append(
            {"at": _utc_now(), "from": previous, "to": current, "reason": str(reason or "").strip()}
        )
        goal["priority"] = current
        goal["updated_at"] = _utc_now()
        self._save()
        return dict(goal)

    def issue_candidate(self, goal_id: str) -> dict[str, Any]:
        goal = self.state["goals"].get(goal_id)
        if not goal:
            raise KeyError(goal_id)
        criteria = "\n".join(f"- {item}" for item in goal.get("success_criteria") or []) or "- Verified objective completion"
        boundaries = "\n".join(f"- {item}" for item in goal.get("protected_boundaries") or []) or "- Existing Genesis autonomy boundaries remain authoritative"
        body = (
            "<!-- genesis-owner-goal -->\n"
            f"Genesis-Owner-Goal: {goal_id}\n\n"
            f"### Goal\n{goal['objective']}\n\n"
            f"### Success criteria\n{criteria}\n\n"
            f"### Protected boundaries\n{boundaries}\n\n"
            "Genesis chooses implementation details autonomously inside approved boundaries. "
            "Escalate only owner-authority decisions or genuine ambiguity."
        )
        severity = "high" if int(goal.get("priority", 50)) >= 80 else "medium"
        return build_agentic_candidate(
            lane="owner-goal",
            title=f"[Genesis Goal] {goal['title']}"[:240],
            body=body,
            labels=["genesis-autonomous", "owner-priority"],
            severity=severity,
            value_score=float(goal.get("priority", 50)),
            bypass_backlog=int(goal.get("priority", 50)) >= 90,
        )

    def attach_issue(self, goal_id: str, issue_number: int) -> None:
        goal = self.state["goals"].get(goal_id)
        if not goal:
            raise KeyError(goal_id)
        number = int(issue_number)
        if number > 0 and number not in goal["issue_numbers"]:
            goal["issue_numbers"].append(number)
            goal["updated_at"] = _utc_now()
            self._save()

    def record_evidence(self, goal_id: str, *, kind: str, reference: str, status: str, summary: str) -> None:
        goal = self.state["goals"].get(goal_id)
        if not goal:
            raise KeyError(goal_id)
        goal["evidence"].append(
            {
                "at": _utc_now(),
                "kind": str(kind).strip(),
                "reference": str(reference).strip(),
                "status": str(status).strip(),
                "summary": str(summary).strip(),
            }
        )
        goal["updated_at"] = _utc_now()
        self._save()

    def escalate(
        self,
        goal_id: str,
        *,
        reason: str,
        requires_owner_authority: bool = False,
        ambiguity: bool = False,
    ) -> bool:
        if not requires_owner_authority and not ambiguity:
            return False
        goal = self.state["goals"].get(goal_id)
        if not goal:
            raise KeyError(goal_id)
        goal["escalations"].append(
            {
                "at": _utc_now(),
                "reason": str(reason).strip(),
                "requires_owner_authority": bool(requires_owner_authority),
                "ambiguity": bool(ambiguity),
                "status": "open",
            }
        )
        goal["updated_at"] = _utc_now()
        self._save()
        return True

    def report(self, goal_id: str, *, metrics: dict[str, Any] | None = None) -> dict[str, Any]:
        goal = self.state["goals"].get(goal_id)
        if not goal:
            raise KeyError(goal_id)
        evidence = list(goal.get("evidence") or [])
        escalations = [row for row in goal.get("escalations") or [] if row.get("status") == "open"]
        return {
            "goal_id": goal_id,
            "title": goal.get("title"),
            "objective": goal.get("objective"),
            "priority": goal.get("priority"),
            "status": goal.get("status"),
            "traceability": {
                "issues": list(goal.get("issue_numbers") or []),
                "priority_history": list(goal.get("priority_history") or []),
            },
            "evidence": evidence,
            "evidence_summary": {
                "total": len(evidence),
                "validated": sum(1 for row in evidence if row.get("status") in {"success", "validated", "complete"}),
            },
            "human_decisions_required": escalations,
            "metrics": dict(metrics or {}),
        }

    def complete_if_verified(self, goal_id: str) -> bool:
        goal = self.state["goals"].get(goal_id)
        if not goal:
            raise KeyError(goal_id)
        evidence = list(goal.get("evidence") or [])
        if not evidence or not all(row.get("status") in {"success", "validated", "complete"} for row in evidence):
            return False
        if any(row.get("status") == "open" for row in goal.get("escalations") or []):
            return False
        goal["status"] = "complete"
        goal["completed_at"] = _utc_now()
        goal["updated_at"] = _utc_now()
        self._save()
        return True
