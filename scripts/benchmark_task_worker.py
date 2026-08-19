from __future__ import annotations

import json
from pathlib import Path

from genesis.benchmark_cycle import advance_one_benchmark


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    print(json.dumps(advance_one_benchmark(root), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
