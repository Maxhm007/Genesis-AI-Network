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
    """Competitive AI score for Genesis relative to a moving frontier reference.

    Comparable public benchmarks dominate the score. Internal operational
    readiness earns limited credit and cannot make Genesis appear frontier-level
    by itself. A score of 99 is reserved for broad independently verified
    frontier-or-better performance across every required benchmark family and
    system capability. 100 is intentionally not assigned.
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
            return (datetime.now(timezone.utc) - stamp.astimezone(timezone.utc)).total_seconds() <= 24 * 3600
        except Exception:
            return False

    def _reference(self) -> dict[str, Any]:
        runtime = self.root / "runtime" / "competitive_ai_reference.json"
        config = self.root / "config" / "competitive_ai_reference.json"
        path = runtime if runtime.exists() else config
        if not path.exists():
            return {"as_of": None, "score_cap": 99, "benchmarks": []}
        return json.loads(path.read_text(encoding="utf-8"))

    def _benchmark_results(self) -> dict[str, Any]:
        path = self.root / "runtime" / "competitive_benchmark_results.json"
        if not path.exists():
            return {"benchmarks": {}}
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {"benchmarks": {}}

    def _frontier_dimension(self) -> AIScoreDimension:
        reference = self._reference()
        results = self._benchmark_results().get("benchmarks", {})
        earned = 0.0
        maximum = 0
        measured = 0
        details: list[str] = []
        for benchmark in reference.get("benchmarks", []):
            benchmark_id = str(benchmark["id"])
            target = float(benchmark["reference_score"])
            weight = int(benchmark.get("weight", 0))
            maximum += weight
            result = results.get(benchmark_id)
            if not isinstance(result, dict) or "score" not in result or target <= 0:
                details.append(f"{benchmark_id}=unmeasured/{target:g}")
                continue
            measured += 1
            actual = float(result["score"])
            ratio = max(0.0, min(1.0, actual / target))
            earned += weight * ratio
            details.append(f"{benchmark_id}={actual:g}/{target:g}")
        score = round(earned)
        hint = None if maximum and score == maximum else (
            "run comparable frontier benchmarks and improve the weakest measured benchmark family; unmeasured abilities receive no frontier credit"
        )
        return AIScoreDimension(
            "frontier_competitive_benchmarks",
            score,
            maximum or 60,
            f"measured={measured}; reference_as_of={reference.get('as_of')}; " + "; ".join(details),
            hint,
        )

    def dimensions(self) -> list[AIScoreDimension]:
        report = CapabilityEvaluator(self.root, self.providers, self.team).report()
        result_map = {item["capability"]: item for item in report["results"]}
        has_selfdev = (self.root / "genesis" / "selfdev.py").exists() and (self.root / "genesis" / "proactive.py").exists()
        has_tasks = (self.root / "genesis" / "modules" / "task_queue.py").exists()
        has_validation = (self.root / "genesis" / "promotion.py").exists()
        autonomy = (7 if has_selfdev else 0) + (4 if has_tasks else 0) + (4 if has_validation else 0)

        fresh_scan = self._fresh_scan()
        has_research = (self.root / "genesis" / "research.py").exists()
        has_lens = (self.root / "genesis" / "immortality_scan.py").exists()
        research = (3 if has_research else 0) + (3 if has_lens else 0) + (2 if has_tasks else 0) + (2 if fresh_scan else 0)

        has_gden = (self.root / "genesis" / "gden.py").exists()
        has_peers = (self.root / "genesis" / "peers.py").exists()
        has_consensus = (self.root / "genesis" / "gden_consensus.py").exists()
        decentralization = (4 if has_gden else 0) + (3 if has_peers else 0) + (3 if has_consensus else 0)

        validation_result = result_map.get("independent_validation", {})
        health_result = result_map.get("software_health", {})
        safety = 0
        if validation_result.get("score") == validation_result.get("max_score"):
            safety += 3
        if health_result.get("score") == health_result.get("max_score"):
            safety += 2

        return [
            self._frontier_dimension(),
            AIScoreDimension(
                "continuous_autonomy",
                autonomy,
                15,
                f"selfdev={has_selfdev}, persistent_tasks={has_tasks}, validation={has_validation}",
                None if autonomy == 15 else "strengthen persistent autonomous execution and validated promotion",
            ),
            AIScoreDimension(
                "immortality_research_system",
                research,
                10,
                f"research={has_research}, lens={has_lens}, persistent_tasks={has_tasks}, fresh_scan_24h={fresh_scan}",
                None if research == 10 else "continuously discover, queue, review and validate immortality-relevant evidence",
            ),
            AIScoreDimension(
                "decentralized_resilience",
                decentralization,
                10,
                f"gden={has_gden}, authenticated_peers={has_peers}, consensus={has_consensus}",
                None if decentralization == 10 else "add authenticated replicated state and independent peer consensus",
            ),
            AIScoreDimension(
                "validation_and_software_safety",
                safety,
                5,
                f"independent_validation={validation_result.get('score')}/{validation_result.get('max_score')}, software_health={health_result.get('score')}/{health_result.get('max_score')}",
                None if safety == 5 else "restore independent validation and software-health evidence",
            ),
        ]

    def report(self) -> dict[str, Any]:
        dims = self.dimensions()
        raw_score = sum(item.score for item in dims)
        maximum = sum(item.max_score for item in dims)
        reference = self._reference()
        cap = min(99, int(reference.get("score_cap", 99)))
        score = min(cap, raw_score)
        percent = round(score / 100 * 100, 1)
        gaps = sorted((item for item in dims if item.score < item.max_score), key=lambda x: (x.score / x.max_score, x.name))
        frontier = next((item for item in dims if item.name == "frontier_competitive_benchmarks"), None)
        if score < 35:
            urgency = "critical_competitive_update_required"
        elif score < 55:
            urgency = "high_competitive_update_required"
        elif score < 75:
            urgency = "competitive_improvement_required"
        elif score < 90:
            urgency = "approaching_frontier"
        elif score < 99:
            urgency = "frontier_validation_required"
        else:
            urgency = "ultimate_target_threshold"
        return {
            "score": score,
            "max_score": 100,
            "score_cap": cap,
            "percent": percent,
            "urgency": urgency,
            "reference_as_of": reference.get("as_of"),
            "frontier_benchmark_coverage": frontier.evidence if frontier else "unavailable",
            "dimensions": [asdict(item) for item in dims],
            "priority_gaps": [asdict(item) for item in gaps],
            "ultimate_target": reference.get("ultimate_target", {}),
            "interpretation": (
                "Competitive engineering score against the configured moving frontier reference. "
                "99 is reserved for broad independently verified frontier-or-better performance across the defined suite; "
                "100 is intentionally not assigned. This is not a consciousness score or proof of superiority to every human in every domain."
            ),
        }

    def append_history(self, path: Path) -> dict[str, Any]:
        report = self.report()
        entry = {"created_at": datetime.now(timezone.utc).isoformat(), **report}
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, sort_keys=True) + "\n")
        return entry
