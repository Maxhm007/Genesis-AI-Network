from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .capabilities import CapabilityEvaluator
from .modules.runtime import ModularGenesis
from .selfdev import SelfDevelopmentExecutor, SelfDevResult


@dataclass(frozen=True)
class DevelopmentPlan:
    title: str
    rationale: str
    proposal: dict


class ProactiveDevelopmentLoop:
    """Choose and execute one bounded improvement at a time.

    Genesis first applies explicitly catalogued bootstrap improvements. Once
    those are complete, measured capability gaps may produce bounded module
    manifest additions. They still travel through SelfDevelopmentExecutor and
    the independent validation/promotion path before reaching main.
    """

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.executor = SelfDevelopmentExecutor(self.root)

    def capability_report(self) -> dict:
        return CapabilityEvaluator(self.root).report()

    def inspect(self) -> list[dict]:
        checks = [
            {
                "capability": "runtime_health_snapshot",
                "present": (self.root / "genesis" / "health.py").exists(),
                "priority": 100,
            },
            {
                "capability": "bounded_cycle_budget",
                "present": (self.root / "genesis" / "budget.py").exists(),
                "priority": 90,
            },
            {
                "capability": "communication_bridge",
                "present": (self.root / "genesis" / "communication.py").exists(),
                "priority": 95,
            },
            {
                "capability": "capability_measurement",
                "present": (self.root / "genesis" / "capabilities.py").exists(),
                "priority": 95,
            },
            {
                "capability": "modular_intelligence_architecture",
                "present": (self.root / "config" / "modules.json").exists(),
                "priority": 95,
            },
        ]
        report = self.capability_report()
        for result in report["results"]:
            checks.append(
                {
                    "capability": "measured:" + result["capability"],
                    "present": result["score"] == result["max_score"],
                    "priority": 80 if result["status"] in {"missing", "failing"} else 60,
                    "score": result["score"],
                    "max_score": result["max_score"],
                    "status": result["status"],
                    "improvement_hint": result["improvement_hint"],
                }
            )
        return sorted(checks, key=lambda item: item["priority"], reverse=True)

    def _module_evolution_plan(self) -> DevelopmentPlan | None:
        config_path = self.root / "config" / "modules.json"
        if not config_path.exists():
            return None
        modular = ModularGenesis(self.root)
        status = modular.status()
        proposals = status.get("module_change_proposals", [])
        if not proposals:
            return None

        structural = next((item for item in proposals if item.get("action") == "add"), None)
        if structural is None:
            return None
        candidate = dict(structural.get("candidate_manifest", {}))
        if not candidate:
            return None

        payload = json.loads(config_path.read_text(encoding="utf-8"))
        modules = list(payload.get("modules", []))
        module_id = candidate.get("module_id")
        if not module_id or any(item.get("module_id") == module_id for item in modules):
            return None

        # The candidate branch treats the module as active so validators test
        # the exact configuration that would land on main. It is not canonical
        # until the candidate itself passes independent validation and promotion.
        candidate["status"] = "active"
        metadata = dict(candidate.get("metadata", {}))
        metadata["activation_requires_candidate_promotion"] = True
        candidate["metadata"] = metadata
        modules.append(candidate)
        payload["modules"] = modules

        proposal = {
            "title": structural.get("title", "Add Genesis specialist module"),
            "files": {
                "config/modules.json": json.dumps(payload, indent=2, sort_keys=False) + "\n"
            },
        }
        return DevelopmentPlan(
            title=proposal["title"],
            rationale=(
                structural.get("rationale", "Measured capability gap requires a specialist module.")
                + " The module is activated only if the candidate passes the existing independent validator quorum."
            ),
            proposal=proposal,
        )

    def plan_next(self) -> DevelopmentPlan | None:
        proposal = self.executor.next_builtin_improvement()
        title = str(proposal.get("title", ""))
        if title != "Record self-development idle state":
            primary_files = list(dict(proposal.get("files", {})))
            if primary_files and not (self.root / primary_files[0]).exists():
                measured_gaps = self.capability_report()["priority_gaps"][:3]
                return DevelopmentPlan(
                    title=title or "Genesis bounded improvement",
                    rationale=(
                        "Genesis detected an executable bounded runtime improvement during "
                        "self-inspection. Current measured gaps: "
                        + ", ".join(item["capability"] for item in measured_gaps)
                    ),
                    proposal=proposal,
                )

        return self._module_evolution_plan()

    def develop_once(self) -> tuple[DevelopmentPlan | None, SelfDevResult | None]:
        plan = self.plan_next()
        if plan is None:
            return None, None
        result = self.executor.execute(plan.proposal)
        return plan, result
