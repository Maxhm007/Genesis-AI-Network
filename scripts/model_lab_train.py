from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from genesis.model_training import ModelTrainingLane, TrainingBudget, TrainingRequest


def main() -> int:
    parser = argparse.ArgumentParser(description="Run one bounded Genesis Model Lab training job")
    parser.add_argument("--model-id", required=True)
    parser.add_argument("--base-path", required=True, help="Path relative to GENESIS_MODEL_BASE_ROOT")
    parser.add_argument("--dataset-path", required=True, help="JSONL path relative to GENESIS_MODEL_DATASET_ROOT")
    parser.add_argument("--capability", action="append", dest="capabilities", default=[])
    parser.add_argument("--max-steps", type=int, default=100)
    parser.add_argument("--max-examples", type=int, default=2000)
    parser.add_argument("--max-sequence-length", type=int, default=2048)
    parser.add_argument("--wall-seconds", type=int, default=7200)
    parser.add_argument("--max-output-bytes", type=int, default=8 * 1024 * 1024 * 1024)
    parser.add_argument("--learning-rate", type=float, default=2e-4)
    parser.add_argument("--gradient-accumulation-steps", type=int, default=8)
    parser.add_argument("--lora-rank", type=int, default=16)
    parser.add_argument("--lora-alpha", type=int, default=32)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    budget = TrainingBudget(
        max_steps=args.max_steps,
        max_examples=args.max_examples,
        max_sequence_length=args.max_sequence_length,
        wall_seconds=args.wall_seconds,
        max_output_bytes=args.max_output_bytes,
        learning_rate=args.learning_rate,
        gradient_accumulation_steps=args.gradient_accumulation_steps,
        lora_rank=args.lora_rank,
        lora_alpha=args.lora_alpha,
    )
    request = TrainingRequest(
        model_id=args.model_id,
        base_path=args.base_path,
        dataset_path=args.dataset_path,
        capabilities=tuple(args.capabilities or ["reasoning", "coding"]),
        budget=budget,
    )
    lane = ModelTrainingLane(root)
    readiness = lane.readiness(request)
    if args.dry_run or not readiness["ready"]:
        print(json.dumps({"status": "ready" if readiness["ready"] else "not_ready", "readiness": readiness}, indent=2, sort_keys=True))
        return 0 if readiness["ready"] else 2

    try:
        result = lane.run(request)
    except Exception as exc:
        print(
            json.dumps(
                {"status": "training_failed", "error": f"{type(exc).__name__}: {exc}"},
                indent=2,
                sort_keys=True,
            )
        )
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result.get("status") == "tested" else 2


if __name__ == "__main__":
    sys.exit(main())
