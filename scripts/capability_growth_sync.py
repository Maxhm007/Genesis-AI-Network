from __future__ import annotations

import json
from pathlib import Path

from genesis.capability_integration import CapabilityGrowthCoordinator
from genesis.efficiency import EfficiencyTracker


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    runtime = root / "runtime"
    runtime.mkdir(parents=True, exist_ok=True)
    tracker = EfficiencyTracker(runtime / "efficiency.jsonl")
    coordinator = CapabilityGrowthCoordinator(root)
    state_path = runtime / "capability_growth_sync.json"

    processed = 0
    if state_path.exists():
        try:
            processed = max(0, int(json.loads(state_path.read_text(encoding="utf-8")).get("processed_records", 0)))
        except Exception:
            processed = 0

    rows = tracker.records()
    results = []
    for index, row in enumerate(rows[processed:], start=processed):
        baseline = coordinator.telemetry.summary(row.provider).get("average_quality", 0.0) or 0.0
        result = coordinator.observe_provider(
            provider=row.provider,
            capability=row.task_type,
            score=row.quality,
            max_score=1.0,
            baseline_score=float(baseline),
            resource_cost=row.compute_units,
            success=row.success,
            evidence_count=1,
            source="runtime/efficiency.jsonl",
            provenance=f"efficiency-record:{index}:{row.created_at}",
        )
        results.append(result)

    state = {
        "processed_records": len(rows),
        "new_records": len(results),
        "providers": sorted({row.provider for row in rows}),
        "routing_profiles_ready": [
            provider
            for provider in sorted({row.provider for row in rows})
            if coordinator.telemetry.summary(provider).get("routing_ready")
        ],
    }
    state_path.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(state, indent=2, sort_keys=True))
