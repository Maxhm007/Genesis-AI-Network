from __future__ import annotations

import json
from pathlib import Path

from genesis.scorecard import GenesisScorecard


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    report = GenesisScorecard(root).write(root / "runtime" / "system_scorecard.json")
    print(json.dumps(report, indent=2, sort_keys=True))
