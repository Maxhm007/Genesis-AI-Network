from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .capabilities import CapabilityEvaluator
from .selfdev import SelfDevelopmentExecutor, SelfDevResult


@dataclass(frozen=True)
class DevelopmentPlan:
    title: str
    rationale: str
    proposal: dict


class ProactiveDevelopmentLoop:
    """Choose and execute one bounded improvement at a time.

    Genesis combines concrete file/runtime checks with its operational
    capability report. Unknown or unsafe gaps are recorded for later model/team
    work; only catalogued bounded changes are executed automatically.
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

    def plan_next(self) -> DevelopmentPlan | None:
        # Measured gaps can guide future work, but only a concrete bounded
        # proposal from the approved bootstrap catalog may execute automatically.
        proposal = self.executor.next_builtin_improvement()
        title = str(proposal.get("title", ""))
        if title == "Record self-development idle state":
            return None

        primary_files = list(dict(proposal.get("files", {})))
        if not primary_files:
            return None
        primary_path = self.root / primary_files[0]
        if primary_path.exists():
            return None

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

    def develop_once(self) -> tuple[DevelopmentPlan | None, SelfDevResult | None]:
        plan = self.plan_next()
        if plan is None:
            return None, None
        result = self.executor.execute(plan.proposal)
        return plan, result
