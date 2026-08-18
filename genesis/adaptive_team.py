from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .adaptive_learning import LearningAwareAITeam, classify_domain
from .team import OrchestrationPlan


DOMAIN_REQUIRED_ROLES: dict[str, tuple[str, ...]] = {
    "communication": ("planner",),
    "engineering": ("planner", "engineer", "reviewer"),
    "research": ("planner", "researcher", "reviewer"),
    "model": ("planner", "model_scout", "reviewer"),
    "network": ("planner", "network_steward", "reviewer"),
    "validation": ("planner", "validator", "reviewer"),
    "security": ("planner", "reviewer"),
    "general": ("planner", "reviewer"),
}


class PerformanceAdaptiveAITeam(LearningAwareAITeam):
    """Choose bounded team composition using measured agent performance.

    Learning may reorder or fill optional team slots, but it cannot remove the
    planner, the domain owner, or independent review/validation roles required
    for the task. A role needs repeated evidence before performance history can
    affect composition, preventing one lucky or bad run from reshaping the team.
    """

    min_agent_samples = 2

    def _preferences(self) -> dict[str, Any]:
        if not self.preferences_path.is_file():
            return {}
        try:
            payload = json.loads(self.preferences_path.read_text(encoding="utf-8"))
            return payload if isinstance(payload, dict) else {}
        except Exception:
            return {}

    def _required_roles(self, domain: str) -> list[str]:
        required = list(DOMAIN_REQUIRED_ROLES.get(domain, DOMAIN_REQUIRED_ROLES["general"]))
        if domain == "security" and self._role("specialist_cybersecurity") is not None:
            required.insert(1, "specialist_cybersecurity")
        return [name for name in required if self._role(name) is not None]

    def _ranked_agents(self, domain: str) -> list[str]:
        payload = self._preferences()
        rows = payload.get("domains", {}).get(domain, {}).get("agents") or []
        ranked: list[str] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            name = str(row.get("agent") or "")
            samples = int(row.get("samples") or 0)
            if samples < self.min_agent_samples:
                continue
            if self._role(name) is None or name in ranked:
                continue
            ranked.append(name)
        return ranked

    def plan_task(self, objective: str, context: str = "") -> OrchestrationPlan:
        base = super().plan_task(objective, context)
        domain = classify_domain(f"{objective}\n{context}")
        required = self._required_roles(domain)
        learned = self._ranked_agents(domain)

        selected: list[str] = []

        def add(name: str) -> None:
            if name not in selected and self._role(name) is not None and len(selected) < self.max_roles_per_task:
                selected.append(name)

        # Safety-critical roles are immutable by learning.
        for name in required:
            add(name)

        # Repeated measured performance decides optional slots.
        for name in learned:
            add(name)

        # Preserve the deterministic base plan as fallback when evidence is
        # sparse or learned roles do not fill the bounded team.
        for name in base.role_names:
            add(name)

        reason = base.reason
        if learned:
            reason += (
                f"; adaptive composition domain={domain}; repeated measured agent evidence preferred "
                f"optional roles={','.join(learned)}; required safety roles preserved={','.join(required)}"
            )
        else:
            reason += f"; adaptive composition domain={domain}; insufficient repeated agent evidence, base team preserved"
        return OrchestrationPlan(objective, tuple(selected), reason)
