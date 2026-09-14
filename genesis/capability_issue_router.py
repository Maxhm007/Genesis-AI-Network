from __future__ import annotations

import json
import os
from pathlib import Path
import urllib.error
import urllib.parse
import urllib.request
from typing import Callable

from .modules.task_queue import GenesisTask, PersistentTaskQueue


CAPABILITY_LABEL = "genesis-capability"
PERFORMANCE_LABEL = "performance-indicator"
CONTROL_TITLE_PREFIX = "[Performance Indicator] Capability Benchmark"
SOURCE_MARKER_PREFIX = "<!-- genesis-capability-source:"
ROUTER_PAUSE_PREFIX = "github_capability_issue_router:"
PERFORMANCE_REASON_PREFIX = "performance_indicator:"
TERMINAL_STATES = {"complete", "cancelled"}


GithubRequester = Callable[[str, str, dict | None], object | None]


def _github_request(method: str, path: str, payload: dict | None = None):
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    repo = os.environ.get("GITHUB_REPOSITORY", "").strip()
    if not token or not repo:
        return None
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        f"https://api.github.com/repos/{repo}{path}",
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "Content-Type": "application/json",
            "User-Agent": "Genesis-AI-Network/capability-issue-router",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = response.read().decode("utf-8")
        return json.loads(raw) if raw.strip() else {}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        print(f"Capability indicator router GitHub HTTP {exc.code}: {detail}")
        return None
    except Exception as exc:
        print(f"Capability indicator router GitHub unavailable: {type(exc).__name__}: {exc}")
        return None


def _source_marker(task_id: str) -> str:
    return f"{SOURCE_MARKER_PREFIX}{task_id} -->"


def _is_source_capability_task(task: GenesisTask) -> bool:
    payload = dict(task.payload or {})
    return (
        payload.get("task_type") == "capability_growth"
        and int(payload.get("github_issue_number") or 0) <= 0
        and str(payload.get("source") or "") == "genesis.evolution_learning"
    )


def _benchmark_gap(task: GenesisTask) -> dict:
    value = task.payload.get("benchmark_gap")
    return value if isinstance(value, dict) else {}


def _issue_title(task: GenesisTask) -> str:
    gap = _benchmark_gap(task)
    benchmark = str(gap.get("benchmark_id") or "measured-gap").strip()
    capability = str(task.payload.get("capability_key") or gap.get("capability_key") or "capability").strip()
    baseline = task.payload.get("baseline_score")
    reference = gap.get("reference_score")
    return f"{CONTROL_TITLE_PREFIX} — {capability} / {benchmark}: {baseline} vs {reference}"[:240]


def _issue_body(task: GenesisTask) -> str:
    gap = _benchmark_gap(task)
    benchmark = str(gap.get("benchmark_id") or "")
    capability = str(task.payload.get("capability_key") or gap.get("capability_key") or "")
    generation = int(task.payload.get("capability_generation") or gap.get("growth_generation") or 1)
    baseline = task.payload.get("baseline_score")
    reference = gap.get("reference_score")
    unit = str(gap.get("unit") or "score")
    return (
        f"{_source_marker(task.task_id)}\n"
        "<!-- genesis-performance-indicator -->\n"
        "This record is a performance indicator, not an immediately actionable repair issue. "
        "Benchmark values may improve or regress over time as Genesis evolves.\n\n"
        f"- **Benchmark:** `{benchmark}`\n"
        f"- **Capability:** `{capability}`\n"
        f"- **Measurement generation:** {generation}\n"
        f"- **Measured value:** {baseline} {unit}\n"
        f"- **Reference:** {reference} {unit}\n"
        f"- **Source task:** `{task.task_id}`\n\n"
        "### Classification rule\n"
        "This indicator stays closed and must not enter DevLab, Issue Solver, Agentic Lab, or repair retry lanes. "
        "A separate open issue may be created only when measurement evidence identifies a concrete defect, "
        "missing capability, failed workflow, or bounded implementation task.\n\n"
        "### Measurement context\n"
        f"{task.objective[:8000]}\n"
    )


def _ensure_performance_label(requester: GithubRequester) -> bool:
    labels = requester("GET", "/labels?per_page=100", None)
    if not isinstance(labels, list):
        return False
    if any(isinstance(row, dict) and row.get("name") == PERFORMANCE_LABEL for row in labels):
        return True
    created = requester(
        "POST",
        "/labels",
        {
            "name": PERFORMANCE_LABEL,
            "color": "0969da",
            "description": "Closed benchmark, score, ranking, baseline, or trend measurement; not solver work",
        },
    )
    return isinstance(created, dict) and created.get("name") == PERFORMANCE_LABEL


def _existing_indicator_issues(requester: GithubRequester) -> list[dict]:
    encoded = urllib.parse.quote(PERFORMANCE_LABEL, safe="")
    rows = requester("GET", f"/issues?state=all&labels={encoded}&per_page=100", None)
    if not isinstance(rows, list):
        rows = requester("GET", "/issues?state=all&per_page=100", None)
    if not isinstance(rows, list):
        return []
    return [row for row in rows if isinstance(row, dict) and "pull_request" not in row]


def _find_issue(existing: list[dict], task_id: str) -> dict | None:
    marker = _source_marker(task_id)
    for issue in existing:
        if marker in str(issue.get("body") or ""):
            return issue
    return None


def _ensure_closed_indicator(
    requester: GithubRequester,
    existing: list[dict],
    task: GenesisTask,
) -> dict | None:
    title = _issue_title(task)
    body = _issue_body(task)
    issue = _find_issue(existing, task.task_id)
    if issue is None:
        created = requester(
            "POST",
            "/issues",
            {"title": title, "body": body, "labels": [PERFORMANCE_LABEL]},
        )
        if not isinstance(created, dict) or int(created.get("number") or 0) <= 0:
            return None
        issue = created
        existing.append(issue)

    labels = issue.get("labels") or []
    label_names = {
        str(row.get("name") if isinstance(row, dict) else row)
        for row in labels
        if row
    }
    patch: dict[str, object] = {}
    if str(issue.get("title") or "") != title:
        patch["title"] = title
    if str(issue.get("body") or "") != body:
        patch["body"] = body
    if label_names != {PERFORMANCE_LABEL}:
        patch["labels"] = [PERFORMANCE_LABEL]
    if str(issue.get("state") or "open") != "closed":
        patch["state"] = "closed"
        patch["state_reason"] = "not_planned"
    if patch:
        updated = requester("PATCH", f"/issues/{int(issue['number'])}", patch)
        if isinstance(updated, dict):
            issue = updated
    return issue


def _cancel_task(queue: PersistentTaskQueue, task: GenesisTask, reason: str) -> GenesisTask:
    if task.state in TERMINAL_STATES:
        return task
    return queue.cancel(task.task_id, reason)


def _cancel_legacy_execution_tasks(
    queue: PersistentTaskQueue,
    source_task_id: str,
    reason: str,
) -> list[str]:
    cancelled: list[str] = []
    for task in queue.list(limit=5000):
        if str(task.payload.get("source_capability_task_id") or "") != source_task_id:
            continue
        if task.payload.get("task_type") != "capability_growth":
            continue
        if task.state in TERMINAL_STATES:
            continue
        queue.cancel(task.task_id, reason)
        cancelled.append(task.task_id)
    return cancelled


def route_capability_growth(
    root: Path,
    *,
    requester: GithubRequester | None = None,
) -> dict:
    """Record benchmark capability gaps as closed indicators, never solver work.

    A changing benchmark score is evidence, not a defect. This router therefore
    terminates legacy capability-growth work and optionally mirrors each
    measurement to a closed GitHub performance-indicator record. Concrete
    remediation must be represented by a separate actionable issue.
    """
    root = Path(root).resolve()
    runtime = root / "runtime"
    runtime.mkdir(parents=True, exist_ok=True)
    queue = PersistentTaskQueue(runtime / "genesis_tasks.sqlite3")
    requester = requester or _github_request

    sources = [task for task in queue.list(limit=5000) if _is_source_capability_task(task)]
    indicators: list[dict] = []
    blocked: list[dict] = []

    github_ready = _ensure_performance_label(requester) if sources else True
    existing = _existing_indicator_issues(requester) if github_ready and sources else []

    for source in sources:
        reason = (
            f"{PERFORMANCE_REASON_PREFIX} benchmark/capability score is a changing measurement, "
            "not an immediately actionable repair task"
        )
        cancelled_execution_tasks = _cancel_legacy_execution_tasks(queue, source.task_id, reason)
        current = queue.get(source.task_id) or source
        if current.state not in TERMINAL_STATES:
            current = _cancel_task(queue, current, reason)

        issue = None
        if github_ready:
            issue = _ensure_closed_indicator(requester, existing, current)
            if issue is None:
                blocked.append({"source_task_id": source.task_id, "reason": "github_indicator_unavailable"})

        indicators.append(
            {
                "source_task_id": source.task_id,
                "source_state": current.state,
                "github_issue_number": int((issue or {}).get("number") or 0),
                "github_issue_url": str((issue or {}).get("html_url") or ""),
                "cancelled_legacy_execution_tasks": cancelled_execution_tasks,
                "classification": PERFORMANCE_LABEL,
            }
        )

    result = {
        "status": "ok" if not blocked else "partial",
        "source_tasks": len(sources),
        "indicators": indicators,
        "routed": [],
        "already_routed": [],
        "skipped_in_flight": [],
        "blocked": blocked,
        "policy": {
            "benchmark_scores_are_performance_indicators": True,
            "performance_indicators_are_closed_by_default": True,
            "performance_indicators_never_create_execution_tasks": True,
            "legacy_capability_growth_execution_is_cancelled": True,
            "concrete_defects_require_separate_actionable_issues": True,
        },
    }
    if sources and not github_ready:
        result["status"] = "partial"
        result["blocked"].append(
            {
                "reason": "github_performance_label_unavailable",
                "note": "runtime tasks were still classified and cancelled safely",
            }
        )

    (runtime / "capability_issue_router.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return result
