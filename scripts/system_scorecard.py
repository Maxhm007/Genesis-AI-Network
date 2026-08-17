from __future__ import annotations

import json
from pathlib import Path

from genesis.competitive_benchmarks import CompetitiveBenchmarkPlanner
from genesis.scorecard import GenesisScorecard


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    benchmark_plan = CompetitiveBenchmarkPlanner(root).ensure_tasks()
    report = GenesisScorecard(root).write(root / "runtime" / "system_scorecard.json")
    report["competitive_benchmark_plan"] = benchmark_plan
    (root / "runtime" / "system_scorecard.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, indent=2, sort_keys=True))
