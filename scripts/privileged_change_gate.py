from __future__ import annotations

import argparse
import json
from pathlib import Path

from genesis.autonomy_guard import AutonomyGuard


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("base_ref", nargs="?", default="origin/main")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    decision = AutonomyGuard(root).analyze_git_candidate(args.base_ref)
    print(json.dumps(decision.as_dict(), indent=2, sort_keys=True))
    if decision.owner_escalation_required or not decision.autonomous_allowed:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
