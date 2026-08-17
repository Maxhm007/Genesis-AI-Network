from __future__ import annotations

import json
from pathlib import Path

from genesis.replication import GeneReplicationManager


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    manager = GeneReplicationManager(root)
    result = {
        "seed_results": manager.seed_first_generation(),
        "status": manager.status(),
    }
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
