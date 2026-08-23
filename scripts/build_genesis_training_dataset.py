from __future__ import annotations

import argparse
import json
from pathlib import Path

from genesis.model_training_dataset import GenesisTrainingDatasetBuilder


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build a provenance-qualified SFT dataset from validated Genesis autonomous promotions."
    )
    parser.add_argument("--root", default=".", help="Genesis repository root")
    parser.add_argument("--head", default="HEAD", help="Git commit/ref that all examples must be ancestors of")
    parser.add_argument("--output-name", default=None, help="Simple .jsonl output file name")
    parser.add_argument("--max-examples", type=int, default=10_000)
    args = parser.parse_args()

    root = Path(args.root).resolve()
    builder = GenesisTrainingDatasetBuilder(root)
    manifest = builder.build(
        head=args.head,
        output_name=args.output_name,
        max_examples=args.max_examples,
    )
    print(json.dumps(manifest, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
