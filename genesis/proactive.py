from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .selfdev import SelfDevelopmentExecutor, SelfDevResult


@dataclass(frozen=True)
class DevelopmentPlan:
    title: str
    rationale: str
    proposal: dict


class ProactiveDevelopmentLoop:
    """Choose and execute one bounded improvement at a time.

    This is intentionally conservative: Genesis proposes a small capability,
    executes it only on a candidate branch through SelfDevelopmentExecutor,
    and leaves promotion to the independent validation path. It never edits
    protected identity files or GitHub workflow permissions.
    """

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.executor = SelfDevelopmentExecutor(self.root)

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
        ]
        return checks

    def plan_next(self) -> DevelopmentPlan | None:
        gaps = [item for item in self.inspect() if not item["present"]]
        if not gaps:
            return None

        proposal = self.executor.next_builtin_improvement()
        title = str(proposal.get("title", "Genesis bounded improvement"))
        return DevelopmentPlan(
            title=title,
            rationale=(
                "Genesis detected a missing bounded runtime capability during "
                "its proactive self-inspection."
            ),
            proposal=proposal,
        )

    def develop_once(self) -> tuple[DevelopmentPlan | None, SelfDevResult | None]:
        plan = self.plan_next()
        if plan is None:
            return None, None
        result = self.executor.execute(plan.proposal)
        return plan, result
