from __future__ import annotations

import json
from pathlib import Path

from genesis.capability_issue_router import route_capability_growth
from genesis.core_processor import GenesisCoreProcessor
from genesis.self_improvement_deduper import dedupe_self_improvement
from genesis.self_improvement_issue_router import route_self_improvement


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    capability_issues = route_capability_growth(root)
    self_improvement_dedupe = dedupe_self_improvement(root)
    self_improvement_issues = route_self_improvement(root)
    processor = GenesisCoreProcessor(root)
    result = processor.cycle()
    result["capability_issue_router"] = capability_issues
    result["self_improvement_dedupe"] = self_improvement_dedupe
    result["self_improvement_issue_router"] = self_improvement_issues
    print(json.dumps(result, indent=2, sort_keys=True))
