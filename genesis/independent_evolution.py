from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .gden import EvolutionLedger, NodeIdentity
from .identity import GeneIdentity
from .peer_network import GenePeerNetwork
from .providers import ProviderRegistry
from .team import AITeam


@dataclass(frozen=True)
class EvolutionProfile:
    logical_id: str
    role: str
    strategy: str
    objective: str


class IndependentGeneEvolution:
    """Independent development loop for one Gene node.

    Each Gene keeps its own development journal, work products and signed ledger.
    Peer knowledge may inform the node, but is never auto-adopted. Structural
    source promotion remains outside this class and still requires the normal
    candidate/test/independent-validator process.
    """

    def __init__(
        self,
        root: Path,
        profile: EvolutionProfile,
        providers: ProviderRegistry | None = None,
    ) -> None:
        self.root = Path(root).resolve()
        self.profile = profile
        self.identity_context = GeneIdentity.load(self.root)
        self.providers = providers or ProviderRegistry()
        self.team = AITeam(self.providers)
        self.node_root = self.root / "runtime" / "grce" / profile.logical_id
        self.node_root.mkdir(parents=True, exist_ok=True)
        self.identity = NodeIdentity.load_or_create(self.node_root / "identity.key")
        self.ledger = EvolutionLedger(self.node_root / "evolution_ledger.jsonl")
        self.peers = GenePeerNetwork(self.root)

    def _peer_context(self) -> list[dict[str, Any]]:
        packets = self.peers.knowledge_feed()
        decisions_path = self.node_root / "knowledge_decisions.jsonl"
        decided: set[str] = set()
        if decisions_path.exists():
            for line in decisions_path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    decided.add(str(json.loads(line).get("packet_id", "")))
        return [item for item in packets if item.get("packet_id") not in decided][-10:]

    def run_cycle(self, objective: str | None = None) -> dict[str, Any]:
        target = objective or self.profile.objective
        peer_context = self._peer_context()
        prompt = (
            "Act as an independent Gene instance. Develop your own solution and improvement path. "
            "Do not copy peer conclusions automatically. Treat peer knowledge as evidence to evaluate. "
            "Produce: current bottleneck, proposed improvement, measurable acceptance criteria, risks, "
            "what peer knowledge (if any) is useful, and what should be shared back with the Gene network. "
            "Do not claim capabilities that were not measured and do not self-promote source changes.\n"
            f"NODE={self.profile.logical_id}\nROLE={self.profile.role}\nSTRATEGY={self.profile.strategy}\n"
            f"OBJECTIVE={target}\nPEER_KNOWLEDGE={json.dumps(peer_context, sort_keys=True)[:12000]}"
        )
        outputs = self.team.run_task(prompt, context=self.identity_context.context_text())
        completed = [item for item in outputs if item.get("status") == "completed"]
        rendered = "\n\n".join(str(item.get("output", "")) for item in completed)
        record = {
            "logical_id": self.profile.logical_id,
            "node_id": self.identity.node_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "objective": target,
            "role": self.profile.role,
            "strategy": self.profile.strategy,
            "peer_packets_considered": [item.get("packet_id") for item in peer_context],
            "outputs": outputs,
            "result": rendered,
            "development_mode": "independent",
            "promotion_rule": "candidate_only_until_tests_and_independent_validator_quorum",
        }
        journal = self.node_root / "independent_evolution.jsonl"
        with journal.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, sort_keys=True) + "\n")
        self.ledger.append(
            self.identity,
            "independent_evolution_cycle_completed",
            {"objective": target, "peer_packets_considered": record["peer_packets_considered"]},
        )
        return record

    def share_result(self, record: dict[str, Any], topic: str = "gene-development") -> dict[str, Any]:
        claim = str(record.get("result", ""))[:8000] or "No provider-backed result available"
        return self.peers.publish_knowledge(
            self.profile.logical_id,
            topic=topic,
            claim=claim,
            evidence={
                "development_mode": record.get("development_mode"),
                "objective": record.get("objective"),
                "provider_outputs": len(record.get("outputs", [])),
            },
            provenance={
                "logical_id": self.profile.logical_id,
                "node_id": self.identity.node_id,
                "created_at": record.get("created_at"),
            },
        )
