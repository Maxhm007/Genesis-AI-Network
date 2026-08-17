from __future__ import annotations

import argparse
import json
from pathlib import Path

from genesis.pulse import GenePulse


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description="Execute exactly one Gene pulse.")
    parser.add_argument("--gene", default="gene-node-1")
    parser.add_argument("--output", default="runtime/pulse_result.json")
    args = parser.parse_args()

    result = GenePulse(ROOT, args.gene).report()
    output = ROOT / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
