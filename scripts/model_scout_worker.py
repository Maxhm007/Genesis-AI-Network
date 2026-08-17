from __future__ import annotations

import json
from pathlib import Path

from genesis.model_scout import ModelScoutModule
from genesis.modules.task_queue import PersistentTaskQueue


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    runtime = root / "runtime"
    runtime.mkdir(parents=True, exist_ok=True)
    scout = ModelScoutModule()
    candidates = scout.load_seed_candidates(root / "config" / "model_candidates.json")
    recommendations = scout.recommend(candidates, capability="reasoning", limit=5)
    report = {
        "candidates": [candidate.as_dict() for candidate in candidates],
        "recommendations": [item.as_dict() for item in recommendations],
        "rule": "Recommendations create evaluation work only. No discovered model may activate without quarantine, tests, benchmark evidence, validation and trust progression.",
    }
    (runtime / "model_scout_recommendations.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    queue = PersistentTaskQueue(runtime / "genesis_tasks.sqlite3")
    created_task = None
    if recommendations:
        top = recommendations[0]
        if top.recommendation == "evaluate_next":
            task, created = queue.create_unique(
                f"model-scout:evaluate:{top.name}",
                f"Evaluate Model Scout recommendation {top.name}. Verify license/provenance, runtime compatibility, resource use, security, and benchmark performance against the current active provider. Do not activate automatically.",
                module_id="genesis.model_scout",
                priority=82,
                payload={
                    "task_type": "model_evaluation",
                    "model_name": top.name,
                    "recommendation": top.recommendation,
                    "source": "model_scout",
                    "use_ai_team": True,
                },
            )
            created_task = {"task_id": task.task_id, "created": created}
    report["evaluation_task"] = created_task
    print(json.dumps(report, indent=2, sort_keys=True))
