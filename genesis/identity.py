from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


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
        payload = json.loads((Path(root) / "GENE_IDENTITY.json").read_text(encoding="utf-8"))
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
