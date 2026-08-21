from __future__ import annotations

import argparse
import json
from pathlib import Path

from genesis.autonomous_engineering import AutonomousEngineeringLoop
from genesis.autonomy_pipeline import PipelineStore
from genesis.evolution_learning import GenesisEvolutionLearningEngine


def main() -> None:
    parser = argparse.ArgumentParser(description="Run one bounded Genesis learning/evolution intake.")
    parser.add_argument("--root", default=".")
    parser.add_argument("--output", default="runtime/evolution/last_learning_cycle.json")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    engineering = AutonomousEngineeringLoop(root)
    pipeline = PipelineStore(root / "runtime" / "genesis_tasks.sqlite3")
    provider = engineering.coding._provider()
    engine = GenesisEvolutionLearningEngine(
        root,
        queue=engineering.queue,
        pipeline=pipeline,
        provider=provider,
    )
    result = engine.run_once()
    output = root / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
