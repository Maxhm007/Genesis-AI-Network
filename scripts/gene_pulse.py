from __future__ import annotations

import argparse
import json
from dataclasses import replace
from pathlib import Path

from genesis.autonomous_engineering import AutonomousEngineeringLoop
from genesis.autonomy_pipeline import PipelineStore
from genesis.evolution_learning import GenesisEvolutionLearningEngine
from genesis.pulse import GenePulse


ROOT = Path(__file__).resolve().parents[1]


class PulseEvolutionLearningEngine(GenesisEvolutionLearningEngine):
    """Keep learning prompts small enough for the bounded local Pulse model."""

    MAX_PULSE_CANDIDATES = 3
    MAX_PULSE_TARGET_BYTES = 700
    MAX_PULSE_LEARNING_BYTES = 900

    def _catalog(self, item):
        query = self._tokens(f"{item.title} {item.summary}")
        compact = []
        for path, text in super()._catalog(item):
            excerpt = text[: self.MAX_PULSE_TARGET_BYTES]
            if not (query & self._tokens(f"{path} {excerpt}")):
                continue
            compact.append((path, excerpt))
            if len(compact) >= self.MAX_PULSE_CANDIDATES:
                break
        return compact

    def _prompt(self, item, catalog):
        compact_item = replace(
            item,
            title=item.title[:300],
            summary=item.summary[: self.MAX_PULSE_LEARNING_BYTES],
        )
        return super()._prompt(compact_item, catalog)


def _run_learning_evolution() -> dict:
    """Learn first, but never let research intake disable the core Pulse."""
    try:
        engineering = AutonomousEngineeringLoop(ROOT)
        pipeline = PipelineStore(ROOT / "runtime" / "genesis_tasks.sqlite3")
        engine = PulseEvolutionLearningEngine(
            ROOT,
            queue=engineering.queue,
            pipeline=pipeline,
            provider=engineering.coding._provider(),
        )
        return engine.run_once()
    except Exception as exc:
        return {
            "status": "learning_cycle_error",
            "error": f"{type(exc).__name__}: {exc}"[:2000],
        }


def main() -> int:
    parser = argparse.ArgumentParser(description="Execute exactly one Gene pulse.")
    parser.add_argument("--gene", default="gene-node-1")
    parser.add_argument("--output", default="runtime/pulse_result.json")
    args = parser.parse_args()

    learning = _run_learning_evolution()
    result = GenePulse(ROOT, args.gene).report()
    result["learning_evolution"] = learning

    process_log = ROOT / "runtime" / "evolution" / "upgrade_process.json"
    if process_log.is_file():
        try:
            result["upgrade_process"] = json.loads(process_log.read_text(encoding="utf-8"))
        except Exception as exc:
            result["upgrade_process"] = {
                "status": "log_read_error",
                "error": f"{type(exc).__name__}: {exc}"[:1000],
            }

    output = ROOT / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
