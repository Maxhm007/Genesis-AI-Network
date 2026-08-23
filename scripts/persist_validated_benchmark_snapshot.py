from __future__ import annotations

import argparse
import json
from pathlib import Path

from genesis.benchmark_state import persist_validated_benchmark_snapshot


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Persist independently validated benchmark artifact state into repository-backed evidence"
    )
    parser.add_argument("--input", required=True, help="Path to competitive_benchmark_results.json from a validated artifact")
    parser.add_argument("--output", default="evidence/validated_benchmark_results.json")
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    payload = persist_validated_benchmark_snapshot(root, Path(args.input))
    output = root / args.output
    if output.resolve() != (root / "evidence" / "validated_benchmark_results.json").resolve():
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
