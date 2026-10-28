"""Build an isolated, reproducible holdout for verified Genesis SFT examples.

Never trains models or promotes adapters. Insufficient evidence stays blocked.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

MIN_EXAMPLES = 30
HOLDOUT_PERCENT = 20


def prepare(dataset: Path, *, min_examples: int = MIN_EXAMPLES) -> dict:
    dataset = Path(dataset).resolve()
    manifest_path = dataset.with_suffix(dataset.suffix + ".manifest.json")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    contents = dataset.read_bytes()
    if hashlib.sha256(contents).hexdigest() != manifest.get("dataset_sha256"):
        raise ValueError("dataset checksum does not match independently generated manifest")
    lines = [json.loads(line) for line in contents.decode("utf-8").splitlines() if line.strip()]
    if len(lines) != manifest.get("example_count"):
        raise ValueError("example count does not match manifest")
    commits, patches = set(), set()
    for row in lines:
        provenance = row.get("provenance") or {}
        if provenance.get("classification") != "genesis_autonomous_validated_promotion":
            raise ValueError("example lacks validated promotion provenance")
        commit = provenance.get("promoted_commit")
        patch = provenance.get("stable_patch_id")
        if not commit or not patch or commit in commits or patch in patches:
            raise ValueError("duplicate or missing commit/patch provenance")
        commits.add(commit)
        patches.add(patch)
    result = {
        "status": "insufficient_examples" if len(lines) < min_examples else "holdout_ready",
        "total": len(lines), "min_examples": min_examples,
        "source_dataset_sha256": manifest["dataset_sha256"],
        "training_started": False, "model_promoted": False,
    }
    if len(lines) >= min_examples:
        ordered = sorted(lines, key=lambda row: hashlib.sha256(
            row["provenance"]["promoted_commit"].encode("ascii")
        ).hexdigest())
        holdout_count = max(1, len(ordered) * HOLDOUT_PERCENT // 100)
        training, holdout = ordered[holdout_count:], ordered[:holdout_count]
        for name, records in (("train", training), ("holdout", holdout)):
            path = dataset.parent / (dataset.stem + f".{name}.jsonl")
            if path.exists():
                raise FileExistsError(f"refusing to overwrite split: {path}")
            path.write_text("".join(json.dumps(item, sort_keys=True) + "\\n" for item in records), encoding="utf-8")
        result.update({"train_examples": len(training), "holdout_examples": len(holdout)})
    output = dataset.parent / (dataset.stem + ".readiness.json")
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\\n", encoding="utf-8")
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", required=True, type=Path)
    parser.add_argument("--min-examples", default=MIN_EXAMPLES, type=int)
    args = parser.parse_args()
    if args.min_examples < MIN_EXAMPLES:
        raise SystemExit(f"minimum must be >= {MIN_EXAMPLES}")
    print(json.dumps(prepare(args.dataset, min_examples=args.min_examples), sort_keys=True))


if __name__ == "__main__":
    main()
