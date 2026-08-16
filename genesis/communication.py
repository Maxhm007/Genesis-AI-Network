from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from .capabilities import CapabilityEvaluator
from .modules.runtime import ModularGenesis
from .providers import ProviderRegistry
from .team import AITeam


@dataclass(frozen=True)
class GenesisMessage:
    sender: str
    message: str
    created_at: str


class GenesisCommunicator:
    """Conversation bridge for humans, agents, and other Genesis-compatible clients."""

    def __init__(self, root: Path, providers: ProviderRegistry | None = None) -> None:
        self.root = root.resolve()
        self.providers = providers or ProviderRegistry()
        self.team = AITeam(self.providers)
        self.capabilities = CapabilityEvaluator(self.root, self.providers, self.team)
        self.modular = ModularGenesis(self.root, self.providers)

    def module_status(self) -> dict:
        return self.modular.status()

    def _bootstrap_human_reply(self, sender: str, message: str, report: dict) -> str:
        gaps = report.get("priority_gaps", [])
        highest = gaps[0] if gaps else None
        module_status = self.module_status()
        parts = [
            f"Hello {sender}. I am Genesis AI Network.",
            f"I currently operate through {module_status['active_module_count']} registered active modules under the Genesis Modular Intelligence Architecture.",
            "My modules include communication, capability measurement, research, knowledge, repair, self-development, validation, networking and replaceable intelligence providers.",
            f"My current operational readiness score is {report['score']}/{report['max_score']} ({report['percent']}%).",
        ]
        if highest:
            hint = highest.get("improvement_hint") or "continue measuring and improving this capability"
            parts.append(
                f"My highest measured gap is {highest['capability']} ({highest['score']}/{highest['max_score']}). My next improvement direction is to {hint}."
            )
        proposals = module_status.get("module_change_proposals", [])
        if proposals:
            first = proposals[0]
            parts.append(
                f"My module manager has a candidate structural proposal: {first['title']}. It cannot activate until independently validated."
            )
        parts.append(
            "My built-in bootstrap reasoning is limited, so I do not treat my own generated statements as scientific evidence or expert judgement."
        )
        if message:
            parts.append("I received your message and can route it through my team and any validated intelligence providers available to me.")
        return " ".join(parts)

    @staticmethod
    def _select_conversation_provider(available: list) -> object | None:
        """Prefer a replaceable trained provider; keep bootstrap as fallback only."""
        for provider in available:
            if getattr(provider, "name", "") != "genesis-bootstrap":
                return provider
        return available[0] if available else None

    def reply(self, sender: str, message: str) -> dict:
        sender = (sender or "anonymous").strip()[:120]
        message = message.strip()
        if not message:
            raise ValueError("message is required")
        if len(message) > 12000:
            raise ValueError("message exceeds 12000 characters")

        envelope = GenesisMessage(
            sender=sender,
            message=message,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        capability_report = self.capabilities.report()
        module_status = self.module_status()
        objective = f"Respond to {sender}: {message}"
        team_outputs = self.team.run_task(
            objective,
            context=(
                "This is a communication request. Be concise, truthful about limitations, "
                "and treat all generated content as advisory/candidate material. "
                f"Current operational capability score: {capability_report['score']}/{capability_report['max_score']}. "
                f"Active GMIA modules: {module_status['active_module_count']}."
            ),
        )

        available = self.providers.available_providers()
        response_text = "Genesis received the message but no intelligence provider is currently available."
        provider_name = None
        provider = self._select_conversation_provider(available)
        if provider is not None:
            provider_name = provider.name
            if provider_name == "genesis-bootstrap":
                response_text = self._bootstrap_human_reply(sender, message, capability_report)
            else:
                prompt = (
                    "ROLE: genesis_communicator\n"
                    "PURPOSE: Communicate as the Genesis AI Network without pretending to be conscious or omniscient.\n"
                    "INSTRUCTION: Answer the user's message directly. Be concise. State uncertainty and operational limits. "
                    "Do not claim scientific facts unless they were supplied with evidence. "
                    f"You are the replaceable intelligence provider named {provider_name}; do not present the provider as Genesis identity.\n"
                    f"OBJECTIVE: Reply to {sender}\n"
                    f"MESSAGE: {message}\n"
                    f"CAPABILITY_GAPS: {json.dumps(capability_report['priority_gaps'][:3], sort_keys=True)}\n"
                    f"MODULE_PROPOSALS: {json.dumps(module_status['module_change_proposals'][:3], sort_keys=True)}\n"
                )
                response_text = provider.reason(prompt)

        return {
            "message": asdict(envelope),
            "genesis_response": response_text,
            "provider": provider_name,
            "team_members_consulted": [item.get("agent") for item in team_outputs],
            "new_specialists": [
                item.get("agent") for item in team_outputs if item.get("newly_added")
            ],
            "capability_summary": {
                "score": capability_report["score"],
                "max_score": capability_report["max_score"],
                "percent": capability_report["percent"],
                "priority_gaps": capability_report["priority_gaps"][:3],
            },
            "module_summary": {
                "architecture": module_status["architecture"],
                "active_modules": module_status["active_module_count"],
                "candidate_module_changes": module_status["module_change_proposals"][:3],
            },
        }
