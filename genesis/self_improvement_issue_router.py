from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import urllib.error
import urllib.parse
import urllib.request
from typing import Callable

from .modules.task_queue import GenesisTask, PersistentTaskQueue


SELF_IMPROVEMENT_LABEL = "genesis-self-improvement"
TITLE_PREFIX = "[Genesis Self Improvement]"
SOURCE_MARKER_PREFIX = "<!-- genesis-self-improvement-source:"
ROUTER_PAUSE_PREFIX = "github_self_improvement_issue_router:"
ROUTABLE_STATES = {"new", "assigned", "blocked", "failed"}
TERMINAL_STATES = {"complete", "quarantined", "cancelled"}
DIRECT_SELF_IMPROVEMENT_TYPES = {
    "competitive_ai_improvement",
    "gene_velocity_improvement",
    "planned_self_improvement",
}


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
            "User-Agent": "Genesis-AI-Network/self-improvement-issue-router",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = response.read().decode("utf-8")
        return json.loads(raw) if raw.strip() else {}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        print(f"Self-improvement issue router GitHub HTTP {exc.code}: {detail}")
        return None
    except Exception as exc:
        print(f"Self-improvement issue router GitHub unavailable: {type(exc).__name__}: {exc}")
        return None


def _source_marker(task_id: str) -> str:
    return f"{SOURCE_MARKER_PREFIX}{task_id} -->"


def _problem_fingerprint(task_id: str) -> str:
    return f"self-improvement:{task_id}"


def _is_source_self_improvement_task(task: GenesisTask) -> bool:
    payload = dict(task.payload or {})
    if int(payload.get("github_issue_number") or 0) > 0:
        return False
    task_type = str(payload.get("task_type") or "").strip()
    source = str(payload.get("source") or "").strip()
    if source == "github_self_improvement_issue":
        return False
    if task_type in DIRECT_SELF_IMPROVEMENT_TYPES:
        return True
    # Research-driven upgrades of an existing Genesis implementation are also
    # self-improvement work. Capability-growth has its own stricter benchmark
    # issue router and new-capability creation remains a separate lane.
    target = str(payload.get("target_path") or "").strip()
    return (
        source == "genesis.evolution_learning"
        and bool(target)
        and task_type not in {"capability_growth", "new_capability"}
    )


def _recoverable_paused(task: GenesisTask) -> bool:
    return task.state == "paused" and str(task.state_reason or "").startswith(ROUTER_PAUSE_PREFIX)


def _safe_target(root: Path, task: GenesisTask) -> str:
    relative = str(task.payload.get("target_path") or "").replace("\\", "/").lstrip("./")
    if not relative:
        return ""
    path = (root / relative).resolve()
    try:
        path.relative_to(root.resolve())
    except ValueError:
        return "!unsafe!"
    return relative if path.is_file() else "!missing!"


def _issue_title(task: GenesisTask) -> str:
    task_type = str(task.payload.get("task_type") or "self_improvement").replace("_", " ")
    objective = " ".join(str(task.objective or "").split())
    suffix = objective[:150] if objective else task.task_id
    return f"{TITLE_PREFIX} {task_type} — {suffix}"[:240]


def _issue_body(task: GenesisTask, target: str) -> str:
    payload = dict(task.payload or {})
    task_type = str(payload.get("task_type") or "self_improvement")
    development_source = str(payload.get("development_source") or payload.get("source") or "genesis")
    target_line = f"- **Target:** `{target}`\n" if target else ""
    context = [str(item) for item in list(payload.get("context_paths") or []) if str(item).strip()]
    context_line = f"- **Context:** {', '.join(f'`{item}`' for item in context[:12])}\n" if context else ""
    acceptance = str(payload.get("acceptance") or payload.get("required_outcome") or "").strip()
    if not acceptance:
        acceptance = (
            "Produce one bounded evidence-driven improvement. Existing tests, Security review, independent "
            "validation, exact candidate promotion, provenance, owner-control, signing and secret boundaries remain mandatory."
        )
    return (
        f"{_source_marker(task.task_id)}\n"
        "GitHub is the authoritative execution lane for this Genesis self-improvement task. "
        "Genesis may detect and describe the improvement internally, but it must not execute the same work through a parallel direct lane.\n\n"
        f"Genesis-Problem-Fingerprint: {_problem_fingerprint(task.task_id)}\n"
        f"- **Source task:** `{task.task_id}`\n"
        f"- **Task type:** `{task_type}`\n"
        f"- **Detected by:** `{development_source}`\n"
        f"- **Owning module:** `{task.module_id or 'genesis.self_development'}`\n"
        f"{target_line}"
        f"{context_line}\n"
        "### Objective\n"
        f"{str(task.objective)[:8000]}\n\n"
        "### Acceptance\n"
        f"{acceptance[:6000]}\n\n"
        "### Safety and ownership\n"
        "- The original internal source task is paused once this Issue is durable.\n"
        "- Exactly one issue-backed execution task may represent this source task.\n"
        "- Running/review candidates that started before cutover are not interrupted.\n"
        "- Genesis may inspect, research, score and propose internally; implementation is issue-backed.\n"
        "- Tests, Security, independent validators and exact promotion remain mandatory for code changes.\n"
        "- Protected identity/workflow/signing/secret boundaries cannot be bypassed.\n"
    )


def _ensure_label(requester: GithubRequester) -> bool:
    labels = requester("GET", "/labels?per_page=100", None)
    if not isinstance(labels, list):
        return False
    if any(isinstance(row, dict) and row.get("name") == SELF_IMPROVEMENT_LABEL for row in labels):
        return True
    created = requester(
        "POST",
        "/labels",
        {
            "name": SELF_IMPROVEMENT_LABEL,
            "color": "1d76db",
            "description": "Genesis self-improvement work whose execution is controlled through GitHub Issues",
        },
    )
    return isinstance(created, dict) and created.get("name") == SELF_IMPROVEMENT_LABEL


def _existing_issues(requester: GithubRequester) -> list[dict]:
    encoded = urllib.parse.quote(SELF_IMPROVEMENT_LABEL, safe="")
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
            {"title": title, "body": body, "labels": [SELF_IMPROVEMENT_LABEL]},
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


def _execution_tasks(queue: PersistentTaskQueue, source_task_id: str) -> list[GenesisTask]:
    rows = [
        task
        for task in queue.list(limit=5000)
        if str(task.payload.get("source_self_improvement_task_id") or "") == source_task_id
        and int(task.payload.get("github_issue_number") or 0) > 0
        and str(task.payload.get("source") or "") == "github_self_improvement_issue"
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
    payload = dict(source.payload or {})
    payload.update(
        {
            "source": "github_self_improvement_issue",
            "execution_lane": "github_issue",
            "github_issue_number": issue_number,
            "github_issue_url": str(issue.get("html_url") or ""),
            "source_self_improvement_task_id": source.task_id,
            "problem_fingerprint": _problem_fingerprint(source.task_id),
            "attribution": "genesis_autonomous",
            "golden_path": True,
            "work_generation": 1,
            "close_github_issue_after_promotion": bool(target),
            "requires_independent_validation": True,
            "score_fabrication_forbidden": True,
        }
    )
    if target:
        payload["target_path"] = target
        context = [target, *list(payload.get("context_paths") or [])]
        payload["context_paths"] = list(dict.fromkeys(str(item) for item in context if str(item).strip()))
    objective = (
        f"Process Genesis self-improvement through GitHub issue #{issue_number}. "
        "The Issue is the authoritative execution record; do not recreate a parallel direct task.\n\n"
        + str(source.objective)
    )
    return queue.create_unique(
        f"github-self-improvement:{issue_number}:source:{source.task_id}",
        objective,
        module_id=source.module_id or "genesis.self_development",
        priority=max(90, int(source.priority)),
        payload=payload,
        max_attempts=max(1, min(20, int(source.max_attempts))),
    )


def create_planned_self_improvement_task(
    root: Path,
    *,
    title: str,
    rationale: str,
    proposal: dict,
    development_source: str,
) -> tuple[GenesisTask | None, bool]:
    """Persist a planner finding without executing its generated candidate directly."""
    root = Path(root).resolve()
    files = dict(proposal.get("files") or {})
    paths = sorted(str(path).replace("\\", "/").lstrip("./") for path in files)
    if not paths:
        return None, False
    digest = hashlib.sha256(
        json.dumps(
            {"title": title, "rationale": rationale, "files": files},
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()[:20]
    target = paths[0] if len(paths) == 1 else ""
    file_review = dict(proposal.get("file_self_review") or {})
    queue = PersistentTaskQueue(root / "runtime" / "genesis_tasks.sqlite3")
    task, created = queue.create_unique(
        f"planned-self-improvement:{digest}",
        (
            f"{title}. {rationale} "
            "Re-evaluate and implement this bounded self-improvement from the current main branch through the GitHub Issue lane only."
        )[:10000],
        module_id="genesis.self_development",
        priority=92,
        max_attempts=5,
        payload={
            "task_type": "planned_self_improvement",
            "source": "genesis.proactive_planner",
            "development_source": development_source,
            "plan_fingerprint": digest,
            "plan_title": title,
            "target_path": target,
            "context_paths": paths,
            "planned_files": paths,
            "file_self_review": file_review,
            "acceptance": (
                "Implement only the bounded improvement described by this Issue, against current main. "
                "Do not blindly replay stale generated code. Full tests, Security and independent validation must pass."
            ),
            "requires_independent_validation": True,
        },
    )
    return task, created


def route_self_improvement(
    root: Path,
    *,
    requester: GithubRequester | None = None,
) -> dict:
    root = Path(root).resolve()
    runtime = root / "runtime"
    runtime.mkdir(parents=True, exist_ok=True)
    evidence_path = runtime / "self_improvement_issue_router.json"
    queue = PersistentTaskQueue(runtime / "genesis_tasks.sqlite3")
    requester = requester or _github_request

    sources = [task for task in queue.list(limit=5000) if _is_source_self_improvement_task(task)]
    if not sources:
        result = {
            "status": "ok",
            "source_tasks": 0,
            "routed": [],
            "already_routed": [],
            "skipped_in_flight": [],
            "blocked": [],
        }
        evidence_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return result

    if not _ensure_label(requester):
        result = {
            "status": "blocked",
            "reason": "GitHub self-improvement label could not be verified or created; source tasks were left untouched",
            "source_tasks": len(sources),
            "routed": [],
            "already_routed": [],
            "skipped_in_flight": [],
            "blocked": [task.task_id for task in sources],
        }
        evidence_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return result

    existing = _existing_issues(requester)
    routed: list[dict] = []
    already_routed: list[dict] = []
    skipped_in_flight: list[str] = []
    blocked: list[dict] = []

    for source in sources:
        execution = _execution_tasks(queue, source.task_id)
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

        target = _safe_target(root, source)
        if target.startswith("!"):
            blocked.append({"source_task_id": source.task_id, "reason": f"invalid_target:{target}"})
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
                    f"{ROUTER_PAUSE_PREFIX}{issue_number}: GitHub Issue is now the exclusive self-improvement execution lane",
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
    }
    evidence_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result
