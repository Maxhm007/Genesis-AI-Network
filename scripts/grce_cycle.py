from __future__ import annotations

import argparse
import json
from pathlib import Path

from genesis.grce import GeneFederation


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--objective",
        default=(
            "Increase Gene's validated capability and development velocity by discovering the highest-leverage weakness, "
            "testing independent solutions, and producing one bounded candidate recommendation."
        ),
    )
    parser.add_argument("--status-only", action="store_true")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    federation = GeneFederation(root)
    if args.status_only:
        federation.provision()
        print(json.dumps(federation.status(), indent=2, sort_keys=True))
        return
    result = federation.cooperative_cycle(args.objective)
    print(json.dumps({
        "cycle_id": result["cycle_id"],
        "objective": result["objective"],
        "recommendation": result["recommendation"],
        "promotion_rule": result["promotion_rule"],
        "replication_rule": result["replication_rule"],
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
