from __future__ import annotations

import json
import os
from pathlib import Path
import urllib.error
import urllib.request

from genesis.capability_issue_router import route_capability_growth
from genesis.core_processor import GenesisCoreProcessor
from genesis.github_issue_task_router import route_unbacked_tasks
from genesis.issue_backpressure import BACKLOG_REDUCTION_MODE_ENV
from genesis.self_improvement_deduper import dedupe_self_improvement
from genesis.self_improvement_issue_router import route_self_improvement


DEFAULT_BACKLOG_REDUCTION_HIGH_WATER = 40


def _truthy(value: object) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _configured_high_water() -> int:
    raw = str(os.environ.get("GENESIS_BACKLOG_REDUCTION_HIGH_WATER", "") or "").strip()
    if not raw:
        return DEFAULT_BACKLOG_REDUCTION_HIGH_WATER
    try:
        value = int(raw)
    except ValueError:
        return DEFAULT_BACKLOG_REDUCTION_HIGH_WATER
    return max(5, min(value, 500))


def _github_open_issue_count(max_pages: int = 5) -> int | None:
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    repo = os.environ.get("GITHUB_REPOSITORY", "").strip()
    if not token or not repo:
        return None
    count = 0
    for page in range(1, max(1, int(max_pages)) + 1):
        request = urllib.request.Request(
            f"https://api.github.com/repos/{repo}/issues?state=open&per_page=100&page={page}",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "Genesis-AI-Network/backlog-reduction-router",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                rows = json.loads(response.read().decode("utf-8"))
        except (OSError, ValueError, urllib.error.URLError):
            return None
        if not isinstance(rows, list):
            return None
        count += sum(1 for row in rows if isinstance(row, dict) and "pull_request" not in row)
        if len(rows) < 100:
            break
    return count


def _backlog_reduction_active(open_issue_count: int | None, *, high_water: int | None = None) -> bool:
    if _truthy(os.environ.get(BACKLOG_REDUCTION_MODE_ENV)):
        return True
    if open_issue_count is None:
        return False
    threshold = _configured_high_water() if high_water is None else max(1, int(high_water))
    return int(open_issue_count) >= threshold


def route_tasks(root: Path, *, open_issue_count: int | None = None) -> dict:
    root = Path(root).resolve()
    if open_issue_count is None:
        open_issue_count = _github_open_issue_count()
    high_water = _configured_high_water()
    backlog_reduction = _backlog_reduction_active(open_issue_count, high_water=high_water)
    previous_mode = os.environ.get(BACKLOG_REDUCTION_MODE_ENV)
    if backlog_reduction:
        os.environ[BACKLOG_REDUCTION_MODE_ENV] = "1"

    try:
        if backlog_reduction:
            deferred = {
                "status": "deferred_backlog_reduction",
                "reason": "existing GitHub Issue backlog is above the reduction high-water mark",
                "open_issue_count": open_issue_count,
                "high_water": high_water,
            }
            capability_issues = dict(deferred)
            self_improvement_issues = dict(deferred)
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
