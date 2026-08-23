from __future__ import annotations

import argparse
import json
from pathlib import Path

from datasets import load_dataset

from genesis.benchmark_evidence_validation import create_vote
from genesis.swe_bench_pro_evidence import (
    SWE_BENCH_PRO_DATASET,
    SWE_BENCH_PRO_REVISION,
    SWEBenchProEvidenceAdapter,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Independently validate staged Genesis benchmark evidence")
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--validator-id", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    candidate_path = Path(args.candidate).resolve()
    candidate = json.loads(candidate_path.read_text(encoding="utf-8"))
    benchmark_id = str(candidate.get("benchmark_id") or "")
    if benchmark_id != "swe_bench_pro":
        raise SystemExit(f"Unsupported benchmark-specific validator: {benchmark_id or 'unknown'}")

    dataset = load_dataset(
        SWE_BENCH_PRO_DATASET,
        split="test",
        revision=SWE_BENCH_PRO_REVISION,
    )
    SWEBenchProEvidenceAdapter(root).verify_against_dataset(
        candidate,
        (dict(row) for row in dataset),
    )

    vote = create_vote(root, candidate_path, args.validator_id)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(vote, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(vote, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
