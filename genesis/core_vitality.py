from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .replication import GeneReplicationManager


@dataclass(frozen=True)
class LoopStatus:
    name: str
    active: bool
    evidence: dict[str, Any]
    reason: str


class CoreVitalityMonitor:
    """Proves that Genesis's three core loops remain active.

    Genesis is operational only when self-development, bounded reproduction
    readiness, and mission execution are all active. A failed loop is a core
    repair condition, not a cosmetic warning.
    """

    REQUIRED = ("self_development", "reproduction", "mission")

    def __init__(self, root: Path) -> None:
        self.root = Path(root).resolve()
        self.runtime = self.root / "runtime"
        self.runtime.mkdir(parents=True, exist_ok=True)

    def _self_development(self) -> LoopStatus:
        policy = (self.root / "SELF_DEVELOPMENT_POLICY.md").exists()
        executor = (self.root / "genesis" / "autonomous_engineering.py").exists() or (self.root / "genesis" / "selfdev.py").exists()
        promotion = (self.root / ".github" / "workflows" / "proactive-development.yml").exists()
        evidence = {
            "self_development_policy": policy,
            "autonomous_engineering": executor,
            "candidate_validation_path": promotion,
        }
        active = all(evidence.values())
        return LoopStatus("self_development", active, evidence, "active" if active else "self-development path incomplete")

    def _reproduction(self) -> LoopStatus:
        manager = GeneReplicationManager(self.root)
        policy = manager.policy
        checks = {parent: manager.can_replicate(parent, 1) for parent in policy.authorized_parents}
        authorized_parent = any(reason != "parent_not_authorized" for allowed, reason in checks.values()) if checks else False
        capacity_or_bound = any(allowed or reason in {"node_limit", "parent_child_limit", "generation_limit"} for allowed, reason in checks.values()) if checks else False
        evidence = {
            "replication_enabled": policy.enabled,
            "authorized_parent_available": authorized_parent,
            "capacity_available_or_bounded_limit": capacity_or_bound,
            "parents": {parent: {"allowed": allowed, "reason": reason} for parent, (allowed, reason) in checks.items()},
        }
        active = bool(policy.enabled and authorized_parent and capacity_or_bound)
        return LoopStatus("reproduction", active, evidence, "active" if active else "authorized reproduction readiness unavailable")

    def _mission(self) -> LoopStatus:
        constitution = self.root / "GENESIS_CONSTITUTION.md"
        block_path = self.root / "GENESIS_BLOCK.json"
        block = json.loads(block_path.read_text(encoding="utf-8")) if block_path.exists() else {}
        expected = block.get("constitution", {}).get("sha256")
        actual = hashlib.sha256(constitution.read_bytes()).hexdigest() if constitution.exists() else None
        constitution_verified = bool(expected and actual and expected == actual)
        current_task = self.root / "CURRENT_TASK.md"
        task_text = current_task.read_text(encoding="utf-8") if current_task.exists() else ""
        mission_work = any(token in task_text.lower() for token in ("research", "learning", "evolution", "self-running", "autonomous"))
        evidence = {
            "constitution_verified": constitution_verified,
            "current_task_present": current_task.exists() and bool(task_text.strip()),
            "mission_work_path_present": mission_work,
        }
        active = all(evidence.values())
        return LoopStatus("mission", active, evidence, "active" if active else "mission execution proof incomplete")

    def evaluate(self) -> dict[str, Any]:
        loops = [self._self_development(), self._reproduction(), self._mission()]
        operational = all(loop.active for loop in loops)
        failed = [loop.name for loop in loops if not loop.active]
        payload = {
            "identity": "Genesis",
            "operational": operational,
            "required_loops": list(self.REQUIRED),
            "repair_priority": "none" if operational else "highest",
            "failed_loops": failed,
            "loops": {
                loop.name: {"active": loop.active, "reason": loop.reason, "evidence": loop.evidence}
                for loop in loops
            },
            "evaluated_at": datetime.now(timezone.utc).isoformat(),
        }
        (self.runtime / "core_vitality.json").write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        if not operational:
            repair = {
                "priority": "highest",
                "kind": "core_vitality_repair",
                "failed_loops": failed,
                "rule": "restore self-development, reproduction readiness, and mission execution before claiming Genesis operational",
            }
            (self.runtime / "core_vitality_repair.json").write_text(json.dumps(repair, indent=2, sort_keys=True), encoding="utf-8")
        return payload
