from __future__ import annotations

import os
import re


DEFAULT_MAX_ACTIVE_AUTONOMOUS_ISSUES = 20
MAX_CONFIGURED_BACKLOG = 500
GENESIS_TASK_MARKER = "<!-- genesis-task-id:"
GENESIS_TASK_LABEL = "genesis-task"

_CAPACITY_LIMITED_TASK_TYPES = frozenset(
    {
        "new_capability",
        "capability_growth",
        "self_improvement",
        "self_upgrade",
        "model_evaluation",
        "frontier_benchmark_measurement",
        "benchmark_runner_integration",
        "competitive_ai_improvement",
        "gene_velocity_improvement",
        "application_development",
    }
)
_BYPASS_TASK_TYPES = frozenset(
    {
        "self_repair",
        "security_repair",
        "action_failure",
        "action_repair",
        "workflow_repair",
        "issue_repair",
    }
)
_RESEARCH_SOURCES = frozenset(
    {
        "genesis.evolution_learning",
        "genesis.research",
        "model_scout",
    }
)
_OWNER_SOURCE_VALUES = frozenset({"owner", "user", "github_issue", "manual", "repository_owner"})
_OWNER_BYPASS_KEYS = (
    "owner_prioritized",
    "owner_assigned",
    "user_created_issue",
    "github_user_created",
    "source_issue_number",
    "github_source_issue_number",
)
_TASK_TYPE_RE = re.compile(r"^- \*\*Task type:\*\* `([^`]+)`", re.MULTILINE)
_SOURCE_RE = re.compile(r"^- \*\*Source:\*\* `([^`]+)`", re.MULTILINE)


def configured_max_active(env: dict[str, str] | None = None) -> int:
    values = os.environ if env is None else env
    raw = str(values.get("GENESIS_MAX_ACTIVE_AUTONOMOUS_ISSUES", "") or "").strip()
    if not raw:
        return DEFAULT_MAX_ACTIVE_AUTONOMOUS_ISSUES
    try:
        parsed = int(raw)
    except ValueError:
        return DEFAULT_MAX_ACTIVE_AUTONOMOUS_ISSUES
    if parsed < 1:
        return DEFAULT_MAX_ACTIVE_AUTONOMOUS_ISSUES
    return min(parsed, MAX_CONFIGURED_BACKLOG)


def _truthy(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value != 0
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def bypasses_backpressure(task) -> bool:
    payload = dict(getattr(task, "payload", {}) or {})
    task_type = str(payload.get("task_type") or "autonomous_task").strip().lower()
    source = str(payload.get("source") or "genesis").strip().lower()
    if task_type in _BYPASS_TASK_TYPES or task_type.endswith("_repair"):
        return True
    if source in _OWNER_SOURCE_VALUES:
        return True
    return any(_truthy(payload.get(key)) for key in _OWNER_BYPASS_KEYS)


def capacity_limited_task(task) -> bool:
    if bypasses_backpressure(task):
        return False
    payload = dict(getattr(task, "payload", {}) or {})
    task_type = str(payload.get("task_type") or "autonomous_task").strip().lower()
    source = str(payload.get("source") or "genesis").strip().lower()
    return task_type in _CAPACITY_LIMITED_TASK_TYPES or source in _RESEARCH_SOURCES


def _label_names(issue: dict) -> set[str]:
    names: set[str] = set()
    for row in issue.get("labels") or []:
        if isinstance(row, dict):
            name = str(row.get("name") or "").strip()
        else:
            name = str(row or "").strip()
        if name:
            names.add(name)
    return names


def _issue_metadata(issue: dict) -> tuple[str, str]:
    body = str(issue.get("body") or "")
    task_match = _TASK_TYPE_RE.search(body)
    source_match = _SOURCE_RE.search(body)
    task_type = task_match.group(1).strip().lower() if task_match else ""
    source = source_match.group(1).strip().lower() if source_match else ""
    return task_type, source


def issue_counts_against_capacity(issue: dict) -> bool:
    if not isinstance(issue, dict) or "pull_request" in issue:
        return False
    if str(issue.get("state") or "").strip().lower() != "open":
        return False
    if GENESIS_TASK_LABEL not in _label_names(issue):
        return False
    body = str(issue.get("body") or "")
    if GENESIS_TASK_MARKER not in body:
        return False
    task_type, source = _issue_metadata(issue)
    if task_type in _BYPASS_TASK_TYPES or task_type.endswith("_repair"):
        return False
    return task_type in _CAPACITY_LIMITED_TASK_TYPES or source in _RESEARCH_SOURCES


def active_capacity_count(issues: list[dict]) -> int:
    return sum(1 for issue in issues if issue_counts_against_capacity(issue))
