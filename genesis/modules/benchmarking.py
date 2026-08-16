from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable
import json


@dataclass(frozen=True)
class BenchmarkResult:
    benchmark_id: str
    module_id: str
    score: float
    max_score: float
    passed: bool
    evidence: dict
    created_at: str

    @property
    def percent(self) -> float:
        return round((self.score / self.max_score) * 100, 2) if self.max_score else 0.0


class BenchmarkEngine:
    """Run repeatable operational benchmarks and preserve evidence.

    A benchmark score is evidence about a defined task only. It is not a claim
    of general intelligence, consciousness, or scientific correctness.
    """

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self._benchmarks: dict[str, tuple[str, Callable[[], tuple[float, float, dict]]]] = {}

    def register(self, benchmark_id: str, module_id: str, probe: Callable[[], tuple[float, float, dict]]) -> None:
        if not benchmark_id.strip():
            raise ValueError("benchmark_id is required")
        if not module_id.startswith("genesis."):
            raise ValueError("module_id must start with genesis.")
        self._benchmarks[benchmark_id] = (module_id, probe)

    def run(self, benchmark_id: str) -> BenchmarkResult:
        if benchmark_id not in self._benchmarks:
            raise KeyError(benchmark_id)
        module_id, probe = self._benchmarks[benchmark_id]
        score, maximum, evidence = probe()
        if maximum <= 0 or score < 0 or score > maximum:
            raise ValueError("benchmark returned invalid score")
        result = BenchmarkResult(
            benchmark_id=benchmark_id,
            module_id=module_id,
            score=float(score),
            max_score=float(maximum),
            passed=score == maximum,
            evidence=dict(evidence),
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        return result

    def run_all(self) -> list[BenchmarkResult]:
        return [self.run(key) for key in sorted(self._benchmarks)]

    @staticmethod
    def compare(before: BenchmarkResult, after: BenchmarkResult) -> dict:
        if before.benchmark_id != after.benchmark_id:
            raise ValueError("benchmark ids must match")
        delta = round(after.percent - before.percent, 2)
        return {
            "benchmark_id": before.benchmark_id,
            "before_percent": before.percent,
            "after_percent": after.percent,
            "delta_percent": delta,
            "improved": delta > 0,
            "regressed": delta < 0,
        }

    def write_report(self, path: Path, results: list[BenchmarkResult]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps([asdict(item) | {"percent": item.percent} for item in results], indent=2), encoding="utf-8")
