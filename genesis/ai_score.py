from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .capabilities import CapabilityEvaluator
from .providers import ProviderRegistry
from .team import AITeam


@dataclass(frozen=True)
class AIScoreDimension:
    name: str
    score: int
    max_score: int
    evidence: str
    improvement_hint: str | None = None


class GenesisAIScorer:
    """Dynamic operational AI score for Genesis.

    This score is deliberately stricter than the basic capability score. It is
    a maintenance signal, not a claim of consciousness, AGI, scientific truth,
    or proximity to physical immortality.
    """

    def __init__(self, root: Path, providers: ProviderRegistry | None = None, team: AITeam | None = None) -> None:
        self.root = root.resolve()
        self.providers = providers or ProviderRegistry()
        self.team = team or AITeam(self.providers)

    def _fresh_scan(self) -> bool:
        path = self.root / "runtime" / "immortality_scan.json"
        if not path.exists():
            return False
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            stamp = datetime.fromisoformat(str(payload["created_at"]).replace("Z", "+00:00"))
            age = datetime.now(timezone.utc) - stamp.astimezone(timezone.utc)
            return age.total_seconds() <= 24 * 3600
        except Exception:
            return False

    def dimensions(self) -> list[AIScoreDimension]:
        report = CapabilityEvaluator(self.root, self.providers, self.team).report()
        result_map = {item["capability"]: item for item in report["results"]}

        def ratio(capability: str, maximum: int) -> int:
            item = result_map[capability]
            return round(maximum * (item["score"] / item["max_score"])) if item["max_score"] else 0

        advanced = result_map["advanced_reasoning"]
        orchestration = result_map["team_orchestration"]
        validation = result_map["independent_validation"]
        health = result_map["software_health"]
        has_research = (self.root / "genesis" / "research.py").exists()
        has_scan_engine = (self.root / "genesis" / "immortality_scan.py").exists()
        fresh_scan = self._fresh_scan()
        has_selfdev = (self.root / "genesis" / "selfdev.py").exists() and (self.root / "genesis" / "proactive.py").exists()
        has_gden = (self.root / "genesis" / "gden.py").exists()
        has_signed_peers = (self.root / "genesis" / "peers.py").exists() and has_gden
        has_task_queue = (self.root / "genesis" / "modules" / "task_queue.py").exists()
        has_benchmarking = (self.root / "genesis" / "modules" / "benchmarking.py").exists()

        research_score = 0
        if has_research:
            research_score += 5
        if has_scan_engine:
            research_score += 5
        if fresh_scan:
            research_score += 5

        autonomy_score = 0
        if has_selfdev:
            autonomy_score += 8
        if has_task_queue:
            autonomy_score += 4
        if has_benchmarking:
            autonomy_score += 3

        decentralization_score = 0
        if has_gden:
            decentralization_score += 7
        if has_signed_peers:
            decentralization_score += 5
        if (self.root / "GDEN_SPEC.md").exists():
            decentralization_score += 3

        return [
            AIScoreDimension(
                "reasoning",
                ratio("advanced_reasoning", 20),
                20,
                f"advanced_reasoning={advanced['score']}/{advanced['max_score']}",
                advanced.get("improvement_hint"),
            ),
            AIScoreDimension(
                "team_orchestration",
                ratio("team_orchestration", 15),
                15,
                f"team_orchestration={orchestration['score']}/{orchestration['max_score']}",
                orchestration.get("improvement_hint"),
            ),
            AIScoreDimension(
                "autonomous_development",
                autonomy_score,
                15,
                f"selfdev={has_selfdev}, persistent_tasks={has_task_queue}, benchmarks={has_benchmarking}",
                None if autonomy_score == 15 else "strengthen persistent benchmark-driven autonomous development",
            ),
            AIScoreDimension(
                "research_freshness",
                research_score,
                15,
                f"research_engine={has_research}, scan_engine={has_scan_engine}, fresh_scan_24h={fresh_scan}",
                None if research_score == 15 else "run current web/scientific discovery and preserve provenance",
            ),
            AIScoreDimension(
                "independent_validation",
                ratio("independent_validation", 10),
                10,
                f"independent_validation={validation['score']}/{validation['max_score']}",
                validation.get("improvement_hint"),
            ),
            AIScoreDimension(
                "decentralization",
                decentralization_score,
                15,
                f"gden={has_gden}, signed_peers={has_signed_peers}",
                None if decentralization_score == 15 else "expand authenticated peer replication and consensus",
            ),
            AIScoreDimension(
                "software_resilience",
                ratio("software_health", 10),
                10,
                f"software_health={health['score']}/{health['max_score']}",
                health.get("improvement_hint"),
            ),
        ]

    def report(self) -> dict[str, Any]:
        dims = self.dimensions()
        score = sum(item.score for item in dims)
        maximum = sum(item.max_score for item in dims)
        percent = round(score / maximum * 100, 1) if maximum else 0.0
        gaps = sorted((item for item in dims if item.score < item.max_score), key=lambda x: (x.score / x.max_score, x.name))
        if percent < 50:
            urgency = "critical_update_required"
        elif percent < 70:
            urgency = "high_priority_update_required"
        elif percent < 85:
            urgency = "improvement_required"
        else:
            urgency = "maintain_and_raise_benchmarks"
        return {
            "score": score,
            "max_score": maximum,
            "percent": percent,
            "urgency": urgency,
            "dimensions": [asdict(item) for item in dims],
            "priority_gaps": [asdict(item) for item in gaps],
            "interpretation": "Operational AI maintenance score only; not consciousness, AGI, scientific truth, or immortality progress.",
        }

    def append_history(self, path: Path) -> dict[str, Any]:
        report = self.report()
        entry = {"created_at": datetime.now(timezone.utc).isoformat(), **report}
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, sort_keys=True) + "\n")
        return entry
