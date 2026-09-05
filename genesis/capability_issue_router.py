from __future__ import annotations

from dataclasses import asdict
import json
import os
from pathlib import Path
import urllib.error
import urllib.parse
import urllib.request
from typing import Callable

from .modules.task_queue import GenesisTask, PersistentTaskQueue


CAPABILITY_LABEL = "genesis-capability"
CONTROL_TITLE_PREFIX = "Genesis Control: Capability Growth"
SOURCE_MARKER_PREFIX = "<!-- genesis-capability-source:"
ROUTER_PAUSE_PREFIX = "github_capability_issue_router:"
ROUTABLE_STATES = {"new", "assigned", "blocked", "failed"}
TERMINAL_STATES = {"complete", "quarantined", "cancelled"}


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
        print(f"Capability issue router GitHub HTTP {exc.code}: {detail}")
        return None
    except Exception as exc:
        print(f"Capability issue router GitHub unavailable: {type(exc).__name__}: {exc}")
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


def _recoverable_paused(task: GenesisTask) -> bool:
    return task.state == "paused" and str(task.state_reason or "").startswith(ROUTER_PAUSE_PREFIX)


def _target_path(root: Path, task: GenesisTask) -> str:
    relative = str(task.payload.get("target_path") or "").replace("\\", "/").lstrip("./")
    if not relative:
        return ""
    path = (root / relative).resolve()
    try:
        path.relative_to(root.resolve())
    except ValueError:
        return ""
    return relative if path.is_file() else ""


def _acceptance(task: GenesisTask) -> str:
    discovery = task.payload.get("discovery")
    if isinstance(discovery, dict):
        finding = discovery.get("finding")
        if isinstance(finding, dict):
            acceptance = str(finding.get("acceptance") or "").strip()
            if acceptance:
                return acceptance[:6000]
    return (
        "Candidate must pass repository tests, Security review and independent validation. "
        "After exact promotion, the same comparable benchmark must be re-measured; capability "
        "credit is allowed only for a real validated improvement over the stored baseline."
    )


def _issue_title(task: GenesisTask) -> str:
    gap = task.payload.get("benchmark_gap") if isinstance(task.payload.get("benchmark_gap"), dict) else {}
    benchmark = str(gap.get("benchmark_id") or "measured-gap").strip()
    capability = str(task.payload.get("capability_key") or gap.get("capability_key") or "capability").strip()
    generation = int(task.payload.get("capability_generation") or gap.get("growth_generation") or 1)
    return f"{CONTROL_TITLE_PREFIX} — {capability} / {benchmark} / generation {generation}"[:240]


def _issue_body(task: GenesisTask, target: str) -> str:
    gap = task.payload.get("benchmark_gap") if isinstance(task.payload.get("benchmark_gap"), dict) else {}
    benchmark = str(gap.get("benchmark_id") or "")
    capability = str(task.payload.get("capability_key") or gap.get("capability_key") or "")
    generation = int(task.payload.get("capability_generation") or gap.get("growth_generation") or 1)
    baseline = task.payload.get("baseline_score")
    reference = gap.get("reference_score")
    unit = str(gap.get("unit") or "score")
    marker = _source_marker(task.task_id)
    fingerprint = f"capability-growth:{benchmark}:generation:{generation}"
    return (
        f"{marker}\n"
        "GitHub is the authoritative execution lane for this bounded Genesis capability addition.\n"
        "The originating benchmark task is paused before any issue-backed coding task becomes eligible, "
        "so the same capability change cannot execute in both the legacy direct lane and GitHub lane.\n\n"
        f"Genesis-Problem-Fingerprint: {fingerprint}\n"
        f"- **Source task:** `{task.task_id}`\n"
        f"- **Benchmark:** `{benchmark}`\n"
        f"- **Capability:** `{capability}`\n"
        f"- **Capability generation:** {generation}\n"
        f"- **Target:** `{target}`\n"
        f"- **Validated baseline:** {baseline} {unit}\n"
        f"- **Reference:** {reference} {unit}\n\n"
        "### Objective\n"
        f"{task.objective[:8000]}\n\n"
        "### Acceptance\n"
        f"{_acceptance(task)}\n\n"
        "### Safety gates\n"
        "- One issue-backed DevLab execution task only; the source task remains paused.\n"
        "- Existing repository tests must pass.\n"
        "- Security and independent validators remain mandatory.\n"
        "- Protected identity/workflow/signing/secret boundaries cannot be bypassed.\n"
        "- Exact candidate promotion is required before this bounded issue may close.\n"
        "- Promotion is not capability credit; post-promotion benchmark evidence must show measured gain.\n"
    )


def _ensure_label(requester: GithubRequester) -> bool:
    labels = requester("GET", "/labels?per_page=100", None)
    if not isinstance(labels, list):
        return False
    if any(isinstance(row, dict) and row.get("name") == CAPABILITY_LABEL for row in labels):
        return True
    created = requester(
        "POST",
        "/labels",
        {
            "name": CAPABILITY_LABEL,
            "color": "5319e7",
            "description": "Genesis capability additions routed through GitHub Issues",
        },
    )
    return isinstance(created, dict) and created.get("name") == CAPABILITY_LABEL


def _existing_capability_issues(requester: GithubRequester) -> list[dict]:
    encoded = urllib.parse.quote(CAPABILITY_LABEL, safe="")
    rows = requester("GET", f"/issues?state=all&labels={encoded}&per_page=100", None)
    if not isinstance(rows, list):
        return []
    return [row for row in rows if isinstance(row, dict) and "pull_request" not in row]


def _find_issue(existing: list[dict], task_id: str) -> dict | None:
    marker = _source_marker(task_id)
    for issue in existing:
        if marker in str(issue.get("body") or ""):
            return issue
    return None


def _ensure_issue(
    requester: GithubRequester,
    existing: list[dict],
    task: GenesisTask,
    target: str,
) -> dict | None:
    issue = _find_issue(existing, task.task_id)
    title = _issue_title(task)
    body = _issue_body(task, target)
    if issue is None:
        created = requester(
            "POST",
            "/issues",
            {"title": title, "body": body, "labels": [CAPABILITY_LABEL]},
        )
        if isinstance(created, dict) and int(created.get("number") or 0) > 0:
            existing.append(created)
            return created
        return None

    patch: dict[str, object] = {}
    if str(issue.get("title") or "") != title:
        patch["title"] = title
    if str(issue.get("body") or "") != body:
        patch["body"] = body
    if str(issue.get("state") or "open") != "open":
        patch["state"] = "open"
    if patch:
        updated = requester("PATCH", f"/issues/{int(issue['number'])}", patch)
        if isinstance(updated, dict):
            issue = updated
    return issue


def _issue_execution_tasks(queue: PersistentTaskQueue, source_task_id: str) -> list[GenesisTask]:
    rows = [
            task
            for task in queue.list(limit=5000)
            if str(task.payload.get('source_capability_task_id') or '') == source_task_id
            and int(task.payload.get('github_issue_number') or 0) > 0
            and task.payload.get('task_type') == 'capability_growth'
        ]
    rows.sort(key=lambda task: (task.created_at, task.task_id))
    return rows


def _create_execution_task(
    queue: PersistentTaskQueue,
    source: GenesisTask,
    issue: dict,
    target: str,
) -> tuple[GenesisTask, bool]:
    issue_number = int(issue.get("number") or 0)
    payload = dict(source.payload)
    payload.update(
        {
            "source": "github_capability_issue",
            "execution_lane": "github_issue",
            "executor": "genesis.devlab",
            "github_issue_number": issue_number,
            "github_issue_url": str(issue.get("html_url") or ""),
            "source_capability_task_id": source.task_id,
            "attribution": "genesis_autonomous",
            "golden_path": True,
            "work_generation": 1,
            "close_github_issue_after_promotion": True,
            "acceptance": _acceptance(source),
            "target_path": target,
            "context_paths": list(dict.fromkeys([target, *list(payload.get("context_paths") or [])])),
            "requires_independent_validation": True,
            "score_fabrication_forbidden": True,
        }
    )
    objective = (
        f"Process Genesis capability addition through GitHub issue #{issue_number}. "
        "The issue is the authoritative execution record; implement exactly one bounded DevLab candidate "
        "against the verified target while preserving all existing safety and validation gates.\n\n"
        + source.objective
    )
    return queue.create_unique(
        f"github-capability-issue:{issue_number}:source:{source.task_id}",
        objective,
        module_id="genesis.coding",
        priority=max(95, int(source.priority)),
        payload=payload,
        max_attempts=max(1, min(20, int(source.max_attempts))),
    )


def route_capability_growth(
    root: Path,
    *,
    requester: GithubRequester | None = None,
) -> dict:
    root = Path(root).resolve()
    queue = PersistentTaskQueue(root / "runtime" / "genesis_tasks.sqlite3")
    requester = requester or _github_request

    sources = [task for task in queue.list(limit=5000) if _is_source_capability_task(task)]
    if not sources:
        result = {
            "status": "ok",
            "source_tasks": 0,
            "routed": [],
            "already_routed": [],
            "skipped_in_flight": [],
            "blocked": [],
        }
        (root / "runtime" / "capability_issue_router.json").write_text(
            json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        return result

    if not _ensure_label(requester):
        result = {
            "status": "blocked",
            "reason": "GitHub capability label could not be verified or created; source tasks were left untouched",
            "source_tasks": len(sources),
            "routed": [],
            "already_routed": [],
            "skipped_in_flight": [],
            "blocked": [task.task_id for task in sources],
        }
        (root / "runtime" / "capability_issue_router.json").write_text(
            json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        return result

    existing = _existing_capability_issues(requester)
    routed: list[dict] = []
    already_routed: list[dict] = []
    skipped_in_flight: list[str] = []
    blocked: list[dict] = []

    for source in sources:
        execution = _issue_execution_tasks(queue, source.task_id)
        if execution:
            already_routed.append(
                {
                    "source_task_id": source.task_id,
                    "execution_task_id": execution[-1].task_id,
                    "github_issue_number": execution[-1].payload.get("github_issue_number"),
                    "execution_state": execution[-1].state,
                }
            )
            continue

        if source.state in {"running", "review"}:
            skipped_in_flight.append(source.task_id)
            continue
        if source.state in TERMINAL_STATES:
            continue
        if source.state == "paused" and not _recoverable_paused(source):
            blocked.append({"source_task_id": source.task_id, "reason": "source_task_paused_for_other_reason"})
            continue
        if source.state not in ROUTABLE_STATES and not _recoverable_paused(source):
            blocked.append({"source_task_id": source.task_id, "reason": f"unsupported_source_state:{source.state}"})
            continue

        target = _target_path(root, source)
        if not target:
            blocked.append({"source_task_id": source.task_id, "reason": "missing_or_unsafe_target"})
            continue

        issue = _ensure_issue(requester, existing, source, target)
        if issue is None:
            blocked.append({"source_task_id": source.task_id, "reason": "github_issue_unavailable"})
            continue
        issue_number = int(issue.get("number") or 0)

        current = queue.get(source.task_id)
        if current is None:
            blocked.append({"source_task_id": source.task_id, "reason": "source_task_disappeared"})
            continue
        if current.state in {"running", "review"}:
            skipped_in_flight.append(source.task_id)
            continue
        if current.state != "paused":
            try:
                current = queue.pause(
                    source.task_id,
                    f"{ROUTER_PAUSE_PREFIX}{issue_number}: GitHub issue is now the exclusive execution lane",
                )
            except Exception as exc:
                blocked.append(
                    {
                        "source_task_id": source.task_id,
                        "github_issue_number": issue_number,
                        "reason": f"pause_failed:{type(exc).__name__}:{exc}",
                    }
                )
                continue

        try:
            execution_task, created = _create_execution_task(queue, current, issue, target)
        except Exception as exc:
            blocked.append(
                {
                    "source_task_id": source.task_id,
                    "github_issue_number": issue_number,
                    "reason": f"execution_task_create_failed:{type(exc).__name__}:{exc}",
                }
            )
            continue

        row = {
            "source_task_id": source.task_id,
            "source_state": current.state,
            "github_issue_number": issue_number,
            "github_issue_url": str(issue.get("html_url") or ""),
            "execution_task_id": execution_task.task_id,
            "execution_state": execution_task.state,
        }
        (routed if created else already_routed).append(row)

    result = {
        "status": "ok" if not blocked else "partial",
        "source_tasks": len(sources),
        "routed": routed,
        "already_routed": already_routed,
        "skipped_in_flight": skipped_in_flight,
        "blocked": blocked,
        "policy": {
            "github_issue_is_exclusive_execution_lane": True,
            "source_task_paused_before_issue_execution": True,
            "running_or_review_legacy_work_is_not_migrated_mid_flight": True,
            "devlab_security_independent_validation_preserved": True,
            "exact_promotion_required_before_issue_close": True,
            "post_promotion_benchmark_gain_required_for_capability_credit": True,
        },
    }
    runtime = root / "runtime"
    runtime.mkdir(parents=True, exist_ok=True)
    (runtime / "capability_issue_router.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return result
