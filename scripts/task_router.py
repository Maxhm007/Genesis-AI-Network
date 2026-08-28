from __future__ import annotations

import json
import os
from pathlib import Path

from genesis.capability_issue_router import route_capability_growth
from genesis.core_processor import GenesisCoreProcessor
from genesis.github_issue_task_router import route_unbacked_tasks
from genesis.issue_backpressure import (
    BACKLOG_REDUCTION_MODE_ENV,
    backlog_reduction_active,
    configured_backlog_reduction_high_water,
    github_open_issue_count,
)
from genesis.self_improvement_backlog_drain import route_existing_self_improvement
from genesis.self_improvement_deduper import dedupe_self_improvement
from genesis.self_improvement_issue_router import route_self_improvement


def route_tasks(root: Path, *, open_issue_count: int | None = None) -> dict:
    root = Path(root).resolve()
    if open_issue_count is None:
        open_issue_count = github_open_issue_count()
    high_water = configured_backlog_reduction_high_water()
    backlog_reduction = backlog_reduction_active(open_issue_count, high_water=high_water)
    previous_mode = os.environ.get(BACKLOG_REDUCTION_MODE_ENV)
    if backlog_reduction:
        os.environ[BACKLOG_REDUCTION_MODE_ENV] = "1"

    try:
        if backlog_reduction:
            capability_issues = {
                "status": "deferred_backlog_reduction",
                "reason": "existing GitHub Issue backlog is above the reduction high-water mark",
                "open_issue_count": open_issue_count,
                "high_water": high_water,
            }
            # Existing specialist Issues are backlog, not new admission. Adopt them
            # into their bounded execution tasks while publication of new
            # self-improvement Issues remains disabled.
            self_improvement_issues = route_existing_self_improvement(root)
        else:
            capability_issues = route_capability_growth(root)
            self_improvement_issues = route_self_improvement(root)

        # Dedupe remains safe/useful during drain mode because it reduces duplicate
        # internal work without creating a new GitHub Issue.
        self_improvement_dedupe = dedupe_self_improvement(root)
        # The general router still runs in reduction mode. Its configured capacity
        # becomes zero only for capacity-limited work; repair/security/action/owner
        # tasks continue through their existing bypass path, and existing Issues are
        # adopted before admission is evaluated.
        github_issue_authority = route_unbacked_tasks(root)
        processor = GenesisCoreProcessor(root)
        result = processor.cycle()
    finally:
        if previous_mode is None:
            os.environ.pop(BACKLOG_REDUCTION_MODE_ENV, None)
        else:
            os.environ[BACKLOG_REDUCTION_MODE_ENV] = previous_mode

    result["backlog_reduction"] = {
        "active": backlog_reduction,
        "open_issue_count": open_issue_count,
        "high_water": high_water,
        "policy": "drain existing Issues before creating new capacity-limited autonomous work",
    }
    result["capability_issue_router"] = capability_issues
    result["self_improvement_dedupe"] = self_improvement_dedupe
    result["self_improvement_issue_router"] = self_improvement_issues
    result["github_issue_task_router"] = github_issue_authority
    return result


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    print(json.dumps(route_tasks(root), indent=2, sort_keys=True))
