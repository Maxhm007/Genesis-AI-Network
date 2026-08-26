from __future__ import annotations

import argparse
import json
from pathlib import Path

from genesis.issue_worker_pool import DEFAULT_MAX_PARALLEL, select_issue_repair_batch


def main() -> None:
    parser = argparse.ArgumentParser(description="Select a bounded Genesis GitHub issue-repair batch.")
    parser.add_argument("--issues-json", required=True, type=Path)
    parser.add_argument("--max-parallel", type=int, default=DEFAULT_MAX_PARALLEL)
    parser.add_argument("--explicit-issue-number", type=int)
    args = parser.parse_args()

    rows = json.loads(args.issues_json.read_text(encoding="utf-8"))
    if not isinstance(rows, list):
        raise SystemExit("issues JSON must contain a list")

    batch = select_issue_repair_batch(
        rows,
        max_parallel=args.max_parallel,
        explicit_issue_number=args.explicit_issue_number,
    )
    print(json.dumps(batch.as_dict(), sort_keys=True, separators=(",", ":")))


if __name__ == "__main__":
    main()
