from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from genesis.modules.task_queue import PersistentTaskQueue
from genesis.velocity import GeneVelocity


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    velocity = GeneVelocity(root)
    report = velocity.report()
    objective = velocity.improvement_objective()
    task_info = None

    if objective:
        queue = PersistentTaskQueue(root / "runtime" / "genesis_tasks.sqlite3")
        day = datetime.now(timezone.utc).date().isoformat()
        task, created = queue.create_unique(
            f"gene-velocity:{day}",
            objective,
            module_id="genesis.capability",
            priority=100,
            payload={
                "task_type": "gene_velocity_improvement",
                "velocity": report,
                "required_outcome": (
                    "Reduce validated development or benchmark/provider-evaluation latency while preserving "
                    "tests, security, provenance, owner authorization, Constitution constraints and independent quorum."
                ),
            },
        )
        task_info = {"task_id": task.task_id, "created": created, "priority": task.priority}

    output = {"velocity": report, "velocity_task": task_info}
    runtime = root / "runtime"
    runtime.mkdir(parents=True, exist_ok=True)
    (runtime / "gene_velocity.json").write_text(json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(output, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
