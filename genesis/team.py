from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable

from .providers import ProviderRegistry


@dataclass(frozen=True)
class AgentRole:
    name: str
    purpose: str
    system_instruction: str


DEFAULT_TEAM: tuple[AgentRole, ...] = (
    AgentRole("planner", "Turn the mission into bounded research/work plans", "Plan small, testable, reversible steps. Respect the Genesis Constitution."),
    AgentRole("researcher", "Find and summarize evidence", "Prefer primary scientific sources. Label uncertainty and contradictions."),
    AgentRole("model_scout", "Evaluate candidate AI capabilities", "Assess license, provenance, hardware needs, safety and usefulness before trust."),
    AgentRole("engineer", "Design candidate software improvements", "Never overwrite stable code directly. Produce isolated candidate proposals."),
    AgentRole("scientist", "Generate testable longevity hypotheses", "Separate established evidence from hypotheses and speculation."),
    AgentRole("reviewer", "Critique research and proposed changes", "Search for errors, unsafe assumptions, weak evidence and hidden dependencies."),
    AgentRole("validator", "Independently validate promotion readiness", "Do not approve merely because another agent recommends approval."),
    AgentRole("network_steward", "Improve resilience and peer coordination", "Prefer decentralization, interoperability, graceful degradation and operator control."),
)


class AITeam:
    """Role-based orchestration over any available intelligence provider.

    With no provider, the team remains defined and records maintenance-mode tasks.
    With providers, roles are routed round-robin so no provider is part of Genesis identity.
    """

    def __init__(self, providers: ProviderRegistry, roles: Iterable[AgentRole] = DEFAULT_TEAM) -> None:
        self.providers = providers
        self.roles = tuple(roles)

    def roster(self) -> list[dict]:
        return [{"name": r.name, "purpose": r.purpose} for r in self.roles]

    def run_task(self, objective: str, context: str = "") -> list[dict]:
        available = self.providers.available_providers()
        now = datetime.now(timezone.utc).isoformat()
        if not available:
            return [{
                "agent": role.name,
                "status": "waiting_for_provider",
                "created_at": now,
                "objective": objective,
            } for role in self.roles]

        outputs: list[dict] = []
        for index, role in enumerate(self.roles):
            provider = available[index % len(available)]
            prompt = (
                f"ROLE: {role.name}\nPURPOSE: {role.purpose}\n"
                f"INSTRUCTION: {role.system_instruction}\n"
                f"OBJECTIVE: {objective}\nCONTEXT:\n{context}\n"
                "Return concise findings, evidence gaps, risks, and the smallest next action."
            )
            try:
                response = provider.reason(prompt)
                outputs.append({"agent": role.name, "provider": provider.name, "status": "completed", "output": response, "created_at": now})
            except Exception as exc:
                outputs.append({"agent": role.name, "provider": provider.name, "status": "error", "error": str(exc), "created_at": now})
        return outputs
