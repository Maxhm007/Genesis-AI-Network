from __future__ import annotations

import json
from pathlib import Path

from genesis.autonomous_engineering import AutonomousEngineeringLoop


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    result = AutonomousEngineeringLoop(root).run_once()
    print(json.dumps(result, indent=2, sort_keys=True))
