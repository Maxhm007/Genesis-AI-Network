from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable

from .providers import ProviderRegistry
from .team import AITeam


@dataclass(frozen=True)
class CapabilityResult:
    capability: str
    score: int
    max_score: int
    status: str
    evidence: str
    improvement_hint: str | None = None


class CapabilityEvaluator:
    """Measure concrete Genesis capabilities and expose prioritized gaps.

    Scores are operational readiness indicators, not claims of intelligence,
    consciousness, expertise, or scientific correctness.
    """

    def __init__(
        self,
        root: Path,
        providers: ProviderRegistry | None = None,
        team: AITeam | None = None,
        test_probe: Callable[[], bool] | None = None,
    ) -> None:
        self.root = root.resolve()
        self.providers = providers or ProviderRegistry()
        self.team = team or AITeam(self.providers)
        self.test_probe = test_probe

    def evaluate(self) -> list[CapabilityResult]:
        available = self.providers.available_providers()
        provider_names = [p.name for p in available]
        trained_or_remote = [name for name in provider_names if name != "genesis-bootstrap"]
        roles = self.team.roles
        dynamic = [role for role in roles if role.dynamic]

        tests_ok = self.test_probe() if self.test_probe is not None else True
        checks = [
            CapabilityResult(
                "bootstrap_reasoning",
                10 if provider_names else 0,
                10,
                "ready" if provider_names else "missing",
                f"available providers: {provider_names}",
                None if provider_names else "restore at least one Genesis intelligence provider",
            ),
            CapabilityResult(
                "advanced_reasoning",
                15 if trained_or_remote else 4,
                15,
                "ready" if trained_or_remote else "limited",
                f"non-bootstrap providers: {trained_or_remote}",
                None if trained_or_remote else "discover and validate a stronger replaceable reasoning provider",
            ),
            CapabilityResult(
                "team_orchestration",
                min(15, 8 + len(dynamic)),
                15,
                "ready" if len(roles) >= 8 else "limited",
                f"roles={len(roles)}, dynamic_specialists={len(dynamic)}",
                None if len(roles) >= 8 else "restore the permanent core AI team",
            ),
            CapabilityResult(
                "communication",
                15 if (self.root / "genesis" / "communication.py").exists() else 0,
                15,
                "ready" if (self.root / "genesis" / "communication.py").exists() else "missing",
                "Genesis message bridge module presence",
                None if (self.root / "genesis" / "communication.py").exists() else "add authenticated message bridge",
            ),
            CapabilityResult(
                "self_development",
                15 if (self.root / "genesis" / "selfdev.py").exists() else 0,
                15,
                "ready" if (self.root / "genesis" / "selfdev.py").exists() else "missing",
                "bounded candidate self-development engine presence",
                None if (self.root / "genesis" / "selfdev.py").exists() else "restore bounded self-development executor",
            ),
            CapabilityResult(
                "independent_validation",
                15 if (self.root / "genesis" / "promotion.py").exists() else 0,
                15,
                "ready" if (self.root / "genesis" / "promotion.py").exists() else "missing",
                "signed promotion/validation module presence",
                None if (self.root / "genesis" / "promotion.py").exists() else "restore independent signed validator quorum",
            ),
            CapabilityResult(
                "software_health",
                15 if tests_ok else 0,
                15,
                "ready" if tests_ok else "failing",
                "test probe passed" if tests_ok else "test probe failed",
                None if tests_ok else "diagnose failing tests through the self-healing loop",
            ),
        ]
        return checks

    def report(self) -> dict:
        results = self.evaluate()
        score = sum(item.score for item in results)
        maximum = sum(item.max_score for item in results)
        gaps = sorted(
            [item for item in results if item.score < item.max_score],
            key=lambda item: (item.score / item.max_score, item.capability),
        )
        return {
            "score": score,
            "max_score": maximum,
            "percent": round((score / maximum) * 100, 1) if maximum else 0.0,
            "results": [asdict(item) for item in results],
            "priority_gaps": [asdict(item) for item in gaps],
            "interpretation": "Operational readiness score only; not a measure of consciousness or general intelligence.",
        }
