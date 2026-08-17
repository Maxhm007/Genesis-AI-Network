from __future__ import annotations

import argparse
import json
from pathlib import Path

from genesis.grce import GeneFederation
from genesis.modules.task_queue import PersistentTaskQueue


def _has_completed_output(result: dict) -> bool:
    for key in ("node_2", "node_3", "node_1"):
        for output in result.get(key, {}).get("outputs", []):
            if output.get("status") == "completed":
                return True
    return False


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--objective",
        default=(
            "Increase Gene's validated capability and development velocity by discovering the highest-leverage weakness, "
            "testing independent solutions, and producing one bounded candidate recommendation."
        ),
    )
    parser.add_argument("--status-only", action="store_true")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    federation = GeneFederation(root)
    if args.status_only:
        federation.provision()
        print(json.dumps(federation.status(), indent=2, sort_keys=True))
        return

    result = federation.cooperative_cycle(args.objective)
    queued = None
    if _has_completed_output(result):
        queue = PersistentTaskQueue(root / "runtime" / "genesis_tasks.sqlite3")
        task, created = queue.create_unique(
            f"grce:{result['cycle_id']}",
            "Implement or experimentally test the bounded GRCE recommendation produced by Gene Nodes 2 and 3, preserving "
            "all normal security, tests, provenance, Constitution constraints, and independent validator quorum.\n\n"
            + result["recommendation"],
            module_id="genesis.coding",
            priority=96,
            payload={
                "task_type": "grce_cooperative_improvement",
                "cycle_id": result["cycle_id"],
                "objective": result["objective"],
                "source": "gene_nodes_2_3_cooperative_cycle",
                "promotion_rule": result["promotion_rule"],
            },
        )
        queued = {"task_id": task.task_id, "created": created}

    print(json.dumps({
        "cycle_id": result["cycle_id"],
        "objective": result["objective"],
        "recommendation": result["recommendation"],
        "queued": queued,
        "promotion_rule": result["promotion_rule"],
        "replication_rule": result["replication_rule"],
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
