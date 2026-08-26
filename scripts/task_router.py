from __future__ import annotations

import json
from pathlib import Path

from genesis.capability_issue_router import route_capability_growth
from genesis.core_processor import GenesisCoreProcessor


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    capability_issues = route_capability_growth(root)
    processor = GenesisCoreProcessor(root)
    result = processor.cycle()
    result["capability_issue_router"] = capability_issues
    print(json.dumps(result, indent=2, sort_keys=True))
