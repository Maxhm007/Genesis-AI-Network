from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from .capabilities import CapabilityEvaluator
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
        objective = f"Respond to {sender}: {message}"
        team_outputs = self.team.run_task(
            objective,
            context=(
                "This is a communication request. Be concise, truthful about limitations, "
                "and treat all generated content as advisory/candidate material. "
                f"Current operational capability score: {capability_report['score']}/{capability_report['max_score']}."
            ),
        )

        available = self.providers.available_providers()
        response_text = "Genesis received the message but no intelligence provider is currently available."
        provider_name = None
        if available:
            provider = available[0]
            provider_name = provider.name
            prompt = (
                "ROLE: genesis_communicator\n"
                "PURPOSE: Communicate as the Genesis AI Network without pretending to be conscious or omniscient.\n"
                "INSTRUCTION: Answer the user's message directly. Be concise. State uncertainty and operational limits. "
                "Do not claim scientific facts unless they were supplied with evidence.\n"
                f"OBJECTIVE: Reply to {sender}\n"
                f"MESSAGE: {message}\n"
                f"CAPABILITY_GAPS: {json.dumps(capability_report['priority_gaps'][:3], sort_keys=True)}\n"
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
        }
