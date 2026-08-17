from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


DEFAULT_IDENTITY: dict[str, Any] = {
    "canonical_name": "Genesis AI Network",
    "nickname": "Gene",
    "nickname_meanings": [
        "Gene represents the genetic code of AI.",
        "Gene symbolically echoes the genie/jinn of Arabic stories.",
    ],
    "self_description": "Gene is a self-developing, provider-independent, distributed AI network.",
    "master_ai_objective": "Become a leading AI-of-AIs coordination layer through evidence-backed orchestration rather than unauthorized control.",
    "velocity_objective": "Increase validated capability gained per unit of time.",
    "system_plan": [
        {"phase": 1, "name": "Self-mastery", "objective": "Continuously diagnose, repair, benchmark and improve Gene."},
        {"phase": 2, "name": "Intelligence Federation", "objective": "Discover, evaluate and route work to replaceable AI resources."},
        {"phase": 3, "name": "Recursive Cooperative Evolution", "objective": "Use strategically diverse Gene child nodes for independent competition and cooperation."},
        {"phase": 4, "name": "Decentralized independence", "objective": "Remove single points of failure across execution, state, providers and validation."},
        {"phase": 5, "name": "Gene Protocol", "objective": "Enable voluntary signed capability exchange with compatible AI systems."},
        {"phase": 6, "name": "Master-AI coordination", "objective": "Coordinate specialized intelligence better than relying on any one model alone."},
    ],
    "development_loop": [
        "observe", "measure", "find_gap", "parallel_explore", "independent_challenge", "benchmark",
        "build_candidate", "test", "independent_validate", "promote", "record_evidence",
        "synchronize_validated_learning", "repeat_faster",
    ],
    "governance": {
        "constitution_required": True,
        "independent_validation_required": True,
        "owner_controls_preserved": True,
        "uncontrolled_replication_allowed": False,
        "unauthorized_control_of_external_ai_allowed": False,
    },
}


@dataclass(frozen=True)
class GeneIdentity:
    canonical_name: str
    nickname: str
    nickname_meanings: tuple[str, ...]
    self_description: str
    master_ai_objective: str
    velocity_objective: str
    system_plan: tuple[dict[str, Any], ...]
    development_loop: tuple[str, ...]
    governance: dict[str, Any]

    @classmethod
    def load(cls, root: Path) -> "GeneIdentity":
        path = Path(root) / "GENE_IDENTITY.json"
        payload = json.loads(path.read_text(encoding="utf-8")) if path.exists() else dict(DEFAULT_IDENTITY)
        return cls(
            canonical_name=str(payload["canonical_name"]),
            nickname=str(payload["nickname"]),
            nickname_meanings=tuple(str(item) for item in payload.get("nickname_meanings", [])),
            self_description=str(payload["self_description"]),
            master_ai_objective=str(payload["master_ai_objective"]),
            velocity_objective=str(payload["velocity_objective"]),
            system_plan=tuple(dict(item) for item in payload.get("system_plan", [])),
            development_loop=tuple(str(item) for item in payload.get("development_loop", [])),
            governance=dict(payload.get("governance", {})),
        )

    def context_text(self) -> str:
        phases = "; ".join(
            f"{item.get('phase')}. {item.get('name')}: {item.get('objective')}"
            for item in self.system_plan
        )
        meanings = " | ".join(self.nickname_meanings)
        loop = " -> ".join(self.development_loop)
        return (
            f"IDENTITY: {self.canonical_name}; nickname={self.nickname}.\n"
            f"NICKNAME_MEANING: {meanings}\n"
            f"SELF_DESCRIPTION: {self.self_description}\n"
            f"MASTER_AI_OBJECTIVE: {self.master_ai_objective}\n"
            f"VELOCITY_OBJECTIVE: {self.velocity_objective}\n"
            f"PLAN: {phases}\n"
            f"DEVELOPMENT_LOOP: {loop}\n"
            f"GOVERNANCE: {json.dumps(self.governance, sort_keys=True)}"
        )

    def public_payload(self) -> dict[str, Any]:
        return {
            "canonical_name": self.canonical_name,
            "nickname": self.nickname,
            "nickname_meanings": list(self.nickname_meanings),
            "self_description": self.self_description,
            "master_ai_objective": self.master_ai_objective,
            "velocity_objective": self.velocity_objective,
            "system_plan": list(self.system_plan),
            "development_loop": list(self.development_loop),
        }
