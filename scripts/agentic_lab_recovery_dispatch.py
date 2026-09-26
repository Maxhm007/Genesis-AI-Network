from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import urllib.error
import urllib.parse
import urllib.request

from genesis.anti_stuck import (
    Attempt,
    anti_stuck_decision,
    attempt_history,
    attempt_marker,
    current_epoch_comments,
    has_state_marker,
    material_state_token,
    materially_equivalent_attempt,
    next_lane_strategy,
    state_marker,
)
from genesis.issue_lifecycle import local_claim_block_reason


ROOT = Path(__file__).resolve().parents[1]
AGENTIC_LABEL = "agentic-lab"
WAITING_CAPABILITY_LABEL = "genesis-waiting-capability"
CAPABILITY_GAP_LABEL = "genesis-capability-gap"
NEEDS_HUMAN_LABEL = "genesis-needs-human"
EXHAUSTED_LABEL = "genesis-solver-exhausted"
ACTIVE_LABELS = {
    "genesis-repair-in-progress",
    "genesis-validating",
    "genesis-working",
    "genesis-verifying",
}
PROTECTED_TARGETS = {
    "genesis/autonomy_guard.py",
    "genesis/autonomy_proof.py",
    "genesis/blockchain.py",
    "genesis/ephemeral_validator.py",
    "genesis/security.py",
    "genesis/selfdev.py",
    "genesis/issue_solver.py",
    "genesis/file_self_review.py",
    "genesis/file_self_review_policy.py",
    "scripts/secret_guard.py",
    "scripts/privileged_change_gate.py",
    "scripts/verify_validator_votes.py",
    "scripts/action_repair_guard.py",
    "scripts/issue_acceptance_guard.py",
}
STRATEGIES = (
    "evidence_first",
    "alternative_implementation",
    "diagnostic_reframe",
    "dependency_diagnosis",
)
STRATEGY_MARKER_PREFIX = "<!-- genesis-agentic-strategy:"
RESULT_MARKER_PREFIX = "<!-- genesis-agentic-strategy-result:"
CAPABILITY_DEPENDENCY_PREFIX = "<!-- genesis-capability-dependency:"
CAPABILITY_RELEASE_PREFIX = "<!-- genesis-agentic-capability-release:"
CAPABILITY_WORK_PREFIX = "<!-- genesis-capability-work:"
HUMAN_MARKER = "<!-- genesis-agentic-needs-human -->"
NON_ACTIONABLE_TASK_TYPES = {
    "frontier_benchmark_measurement",
    "performance_indicator",
    "benchmark_measurement",
    "metric_measurement",
}
NON_ACTIONABLE_MARKER = "<!-- genesis-performance-indicator -->"
INTEGRATION_ROUTE_LABEL = "genesis-integration-route"
INTEGRATION_ROUTE_MARKER = "<!-- genesis-integration-route -->"
INTEGRATION_TASK_TYPES = {
    "benchmark_runner_integration",
    "frontier_benchmark_measurement",
    "competitive_ai_improvement",
    "integration_repair",
}
INTEGRATION_TARGETS = {
    "genesis/benchmark_execution.py",
    "genesis/benchmark_evidence.py",
    "genesis/competitive_benchmarks.py",
    "genesis/evaluation.py",
}

RECOVERY_ENGINE_PATHS = (
    "scripts/agentic_lab_recovery_dispatch.py",
    "scripts/agentic_strategy_repair.py",
    "scripts/github_issue_autorepair.py",
    "genesis/anti_stuck.py",
    "genesis/coding.py",
    "genesis/github_issue_capability_builder.py",
    ".github/workflows/genesis-agentic-lab-recovery.yml",
    ".github/workflows/genesis-agentic-strategy-worker.yml",
    ".github/workflows/genesis-bounded-repair-worker.yml",
)


def request(repository: str, token: str, method: str, path: str, payload: dict | None = None):
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"https://api.github.com/repos/{repository}{path}",
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "Content-Type": "application/json",
            "User-Agent": "Genesis-AI-Network/agentic-lab-strategy-recovery",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            raw = response.read().decode("utf-8")
        return json.loads(raw) if raw.strip() else {}
    except urllib.error.HTTPError as exc:
        if method == "DELETE" and exc.code == 404:
            return {}
        detail = exc.read().decode("utf-8", errors="replace")[:1000]
        raise RuntimeError(f"GitHub HTTP {exc.code} for {method} {path}: {detail}") from exc


def labels(issue: dict) -> set[str]:
    result: set[str] = set()
    for row in issue.get("labels") or []:
        if isinstance(row, dict):
            name = str(row.get("name") or "").strip()
        else:
            name = str(row or "").strip()
        if name:
            result.add(name)
    return result


def issue_task_type(body: str) -> str:
    prefix = "- **Task type:** `"
    for line in str(body or "").splitlines():
        if line.startswith(prefix) and "`" in line[len(prefix):]:
            return line[len(prefix):].split("`", 1)[0].strip().lower()
    return ""


def actionable_issue(issue: dict) -> bool:
    title = str(issue.get("title") or "").strip().lower()
    body = str(issue.get("body") or "")
    if title.startswith("[performance indicator]"):
        return False
    if NON_ACTIONABLE_MARKER in body:
        return False
    if issue_task_type(body) in NON_ACTIONABLE_TASK_TYPES:
        return False
    return True


def explicit_target(body: str) -> str:
    prefix = "- **Target:** `"
    for line in str(body or "").splitlines():
        if line.startswith(prefix) and "`" in line[len(prefix):]:
            return line[len(prefix):].split("`", 1)[0].strip()
    return ""


def safe_lane(target: str) -> str:
    if not target or ".." in Path(target).parts or target in PROTECTED_TARGETS:
        return ""
    if target.startswith("genesis/architecture_extensions/") and target.endswith(".py"):
        return "generic"
    if not (ROOT / target).is_file():
        return ""
    if target.startswith("genesis/") and target.endswith(".py"):
        return "generic"
    if target.startswith("scripts/") and target.endswith(".py"):
        return "specialist"
    return ""


def integration_sensitive(issue: dict, target: str) -> bool:
    body = str(issue.get("body") or "")
    title = str(issue.get("title") or "")
    task_type = issue_task_type(body)
    text = f"{title}\n{body}".lower()
    target_sensitive = target in INTEGRATION_TARGETS
    language_sensitive = (
        ("benchmark" in text and ("integration" in text or "runner" in text or "swe-bench" in text or "swe_bench" in text))
        or ("integration" in text and target.startswith("genesis/"))
    )
    return task_type in INTEGRATION_TASK_TYPES or target_sensitive or language_sensitive


def apply_integration_route(repository: str, token: str, issue: dict, target: str) -> None:
    if not integration_sensitive(issue, target):
        return
    number = int(issue.get("number") or 0)
    if number <= 0:
        return
    body = str(issue.get("body") or "")
    issue_labels = labels(issue)
    if INTEGRATION_ROUTE_MARKER in body and INTEGRATION_ROUTE_LABEL in issue_labels:
        return
    ensure_label(
        repository,
        token,
        INTEGRATION_ROUTE_LABEL,
        "5319e7",
        "Integration-sensitive repair route selected by Agentic Lab",
    )
    guidance = (
        f"{INTEGRATION_ROUTE_MARKER}\n\n"
        "### Genesis integration repair route\n"
        "- **Routing class:** `integration_sensitive`\n"
        + (f"- **Integration target:** `{target}`\n" if target else "")
        + "\nTreat this as integration-sensitive work, not a blind generic retry. Preserve existing public behavior and test ordering first. "
        "Add or isolate the new integration path behind the narrowest condition possible. Use existing validation failures as contracts: "
        "do not reorder unrelated context, weaken tests, or replace working benchmark paths. Prefer an adapter/branch specific to the requested integration. "
        "Add focused regression coverage when allowed, then require the full repository suite before promotion.\n\n"
        "This routing narrows repair strategy only. Security, protected-file boundaries, exact candidate promotion, independent validation, "
        "and verified closure remain mandatory.\n"
    )
    new_body = body.rstrip() + "\n\n" + guidance
    request(repository, token, "PATCH", f"/issues/{number}", {"body": new_body})
    request(repository, token, "POST", f"/issues/{number}/labels", {"labels": [INTEGRATION_ROUTE_LABEL]})

def open_agentic_issues(repository: str, token: str) -> list[dict]:
    encoded = urllib.parse.quote(AGENTIC_LABEL)
    rows: list[dict] = []
    for page in range(1, 101):
        batch = request(
            repository,
            token,
            "GET",
            f"/issues?state=open&labels={encoded}&sort=created&direction=asc&per_page=100&page={page}",
        )
        if not isinstance(batch, list):
            raise RuntimeError("Agentic Lab issue response was not a list")
        rows.extend(
            row
            for row in batch
            if isinstance(row, dict) and not row.get("pull_request") and actionable_issue(row)
        )
        if len(batch) < 100:
            break
    return rows


def remove_label(repository: str, token: str, number: int, label: str) -> None:
    request(repository, token, "DELETE", f"/issues/{number}/labels/{urllib.parse.quote(label, safe='')}")


def ensure_label(repository: str, token: str, name: str, color: str, description: str) -> None:
    try:
        request(repository, token, "POST", "/labels", {"name": name, "color": color, "description": description})
    except RuntimeError as exc:
        if "HTTP 422" not in str(exc):
            raise


def issue_comments(repository: str, token: str, number: int) -> list[dict]:
    rows = request(repository, token, "GET", f"/issues/{number}/comments?per_page=100") or []
    return [row for row in rows if isinstance(row, dict)]


def recovery_engine_generation(root: Path = ROOT) -> str:
    digest = hashlib.sha256()
    for relative in RECOVERY_ENGINE_PATHS:
        path = Path(root) / relative
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        try:
            digest.update(path.read_bytes())
        except OSError:
            digest.update(b"<missing>")
        digest.update(b"\0")
    return digest.hexdigest()[:20]


def recovery_material_state_token(
    issue: dict,
    target: str,
    comments: list[dict],
    *,
    root: Path = ROOT,
) -> str:
    base = material_state_token(issue, target, comments, root=root)
    digest = hashlib.sha256()
    digest.update(base.encode("utf-8"))
    digest.update(b"\0")
    digest.update(recovery_engine_generation(root).encode("utf-8"))
    return digest.hexdigest()[:20]


def ensure_anti_stuck_epoch(
    repository: str,
    token: str,
    issue: dict,
    comments: list[dict],
    target: str,
) -> tuple[str, list[dict]]:
    state_token = recovery_material_state_token(issue, target, comments, root=ROOT)
    has_any_epoch = any(
        "<!-- genesis-anti-stuck-state:" in str(row.get("body") or "")
        for row in comments
    )
    if not has_state_marker(comments, state_token) and has_any_epoch:
        request(
            repository,
            token,
            "POST",
            f"/issues/{int(issue.get('number') or 0)}/comments",
            {
                "body": (
                    f"{state_marker(state_token)}\n"
                    "Genesis Anti-Stuck Controller started a new attempt epoch because "
                    "repository state, issue evidence, or capability-release state materially changed."
                )
            },
        )
        comments = issue_comments(repository, token, int(issue.get("number") or 0))
    return state_token, comments


def _marker_number(text: str, prefix: str) -> int | None:
    match = re.search(re.escape(prefix) + r"(\d+)\s*-->", str(text or ""))
    return int(match.group(1)) if match else None


def capability_dependency_number(comments: list[dict]) -> int | None:
    for row in reversed(comments):
        number = _marker_number(str(row.get("body") or ""), CAPABILITY_DEPENDENCY_PREFIX)
        if number:
            return number
    return None


def unresolved_capability_dependency(comments: list[dict]) -> int | None:
    dependency: int | None = None
    for row in comments:
        body = str(row.get("body") or "")
        found = _marker_number(body, CAPABILITY_DEPENDENCY_PREFIX)
        if found:
            dependency = found
            continue
        released = _marker_number(body, CAPABILITY_RELEASE_PREFIX)
        if released and dependency == released:
            dependency = None
    return dependency


def _latest_release_index(comments: list[dict]) -> int:
    latest = -1
    for index, row in enumerate(comments):
        if str(row.get("body") or "").startswith(CAPABILITY_RELEASE_PREFIX):
            latest = index
    return latest


def attempted_strategies(comments: list[dict]) -> list[str]:
    release_index = _latest_release_index(comments)
    attempted: list[str] = []
    for row in comments[release_index + 1 :]:
        body = str(row.get("body") or "")
        if not body.startswith(STRATEGY_MARKER_PREFIX):
            continue
        strategy = body[len(STRATEGY_MARKER_PREFIX) :].split("-->", 1)[0].strip()
        if strategy in STRATEGIES and strategy not in attempted:
            attempted.append(strategy)
    return attempted


def next_strategy(comments: list[dict]) -> str:
    used = set(attempted_strategies(comments))
    for strategy in STRATEGIES:
        if strategy not in used:
            return strategy
    return ""


def latest_result_status(comments: list[dict], state_token: str = "") -> str:
    scoped = current_epoch_comments(comments, state_token) if state_token else comments[_latest_release_index(comments) + 1 :]
    for row in reversed(scoped):
        body = str(row.get("body") or "")
        if not body.startswith(RESULT_MARKER_PREFIX):
            continue
        match = re.search(r"repair status:\s*`([^`]+)`", body)
        if match:
            return match.group(1).strip()
        return "unknown"
    return ""


def capability_gap_status(status: str) -> bool:
    normalized = str(status or "").strip().lower()
    return normalized in {
        "retry_pending_capability",
        "blocked_no_safe_context",
    }


def _all_issues(repository: str, token: str) -> list[dict]:
    rows: list[dict] = []
    for page in range(1, 101):
        batch = request(repository, token, "GET", f"/issues?state=all&sort=created&direction=asc&per_page=100&page={page}")
        if not isinstance(batch, list):
            raise RuntimeError("GitHub issue response was not a list")
        rows.extend(row for row in batch if isinstance(row, dict) and not row.get("pull_request"))
        if len(batch) < 100:
            break
    return rows


def _capability_class(reason: str) -> str:
    normalized = str(reason or "strategy_set_exhausted").strip().lower().replace(" ", "_")
    return normalized or "strategy_set_exhausted"


def _capability_identity(body: str) -> tuple[str, str]:
    blocked_target = ""
    blocker = ""
    for line in str(body or "").splitlines():
        if line.startswith("- **Blocked target:** `"):
            blocked_target = line.split("`", 2)[1].strip()
        elif line.startswith("- **Observed blocker:** `"):
            blocker = line.split("`", 2)[1].strip()
    return blocked_target, _capability_class(blocker)


def _capability_fingerprint(target: str, reason: str) -> str:
    raw = f"agentic-capability:v2:{target}:{_capability_class(reason)}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:16]


def ensure_capability_issue(
    repository: str,
    token: str,
    issue: dict,
    target: str,
    reason: str,
) -> dict:
    parent_number = int(issue.get("number") or 0)
    capability_class = _capability_class(reason)
    fingerprint = _capability_fingerprint(target, capability_class)
    marker = f"{CAPABILITY_WORK_PREFIX}{fingerprint} -->"

    for row in _all_issues(repository, token):
        row_body = str(row.get("body") or "")
        if marker in row_body:
            return row
        if CAPABILITY_WORK_PREFIX in row_body and _capability_identity(row_body) == (target, capability_class):
            return row

    ensure_label(
        repository,
        token,
        CAPABILITY_GAP_LABEL,
        "5319e7",
        "Genesis capability work required before a blocked parent Issue can resume",
    )

    title = f"[Genesis Capability] Repair {target} blocker: {capability_class}"
    body = (
        f"{marker}\n"
        f"<!-- genesis-capability-parent:{parent_number} -->\n"
        "This capability Issue was created automatically because materially different Agentic Lab repair strategies could not safely complete one or more parent Issues with current Genesis capabilities.\n\n"
        f"- **Parent issue:** #{parent_number}\n"
        f"- **Blocked target:** `{target}`\n"
        f"- **Observed blocker:** `{capability_class}`\n"
        "- **Task type:** `capability_growth`\n"
        "- **Target:** `genesis/github_issue_capability_builder.py`\n\n"
        "### Objective\n"
        "Add the smallest reusable Genesis repair capability that addresses this blocker class without hard-coding any parent Issue. The capability may improve evidence interpretation, repair-plan generation, provider/tool routing, or safe context selection as justified by repository evidence.\n\n"
        "### Acceptance\n"
        "- Capability is reusable for the blocker class, not specific to one Issue number.\n"
        "- Parents with the same blocked target and blocker class reuse this capability Issue instead of creating another one.\n"
        "- Existing tests, Security, protected-file boundaries, signing, validation, exact promotion, secret boundaries, and owner control remain unchanged or stronger.\n"
        "- Add focused regression coverage for the new repair capability.\n"
        "- Close this Issue only after the capability is verified and promoted.\n\n"
        "### Dependency rule\n"
        "Each linked parent remains open but paused. Once this shared capability Issue is verified/completed, Agentic Lab may independently resume every linked parent with a fresh strategy cycle.\n"
    )
    created = request(
        repository,
        token,
        "POST",
        "/issues",
        {
            "title": title[:240],
            "body": body,
            "labels": ["genesis-task", "genesis-repair", "genesis-autonomous", CAPABILITY_GAP_LABEL],
        },
    )
    if not isinstance(created, dict) or not int(created.get("number") or 0):
        raise RuntimeError("GitHub did not return a valid capability Issue")
    return created


def capability_ready(repository: str, token: str, number: int) -> bool:
    issue = request(repository, token, "GET", f"/issues/{int(number)}")
    if not isinstance(issue, dict):
        return False
    issue_labels = labels(issue)
    state = str(issue.get("state") or "").lower()
    reason = str(issue.get("state_reason") or "").lower()
    return "genesis-verified" in issue_labels or (state == "closed" and reason == "completed")


def _post_once(repository: str, token: str, number: int, comments: list[dict], marker: str, body: str) -> None:
    if any(marker in str(row.get("body") or "") for row in comments):
        return
    request(repository, token, "POST", f"/issues/{number}/comments", {"body": body})


def pause_for_capability(
    repository: str,
    token: str,
    issue: dict,
    comments: list[dict],
    target: str,
    reason: str,
) -> dict:
    number = int(issue.get("number") or 0)
    if CAPABILITY_WORK_PREFIX in str(issue.get("body") or ""):
        ensure_label(
            repository,
            token,
            NEEDS_HUMAN_LABEL,
            "d73a4a",
            "Genesis exhausted materially different safe strategies for this capability work; human review is required",
        )
        request(repository, token, "POST", f"/issues/{number}/labels", {"labels": [NEEDS_HUMAN_LABEL, EXHAUSTED_LABEL, AGENTIC_LABEL]})
        for label in ("genesis-repair-in-progress", "genesis-validating", "genesis-autonomous", "genesis-deferred"):
            remove_label(repository, token, number, label)
        _post_once(
            repository,
            token,
            number,
            comments,
            HUMAN_MARKER,
            (
                f"{HUMAN_MARKER}\n"
                "Genesis tried the available materially different Agentic Lab strategies for this capability-building Issue and still could not produce a verified solution. "
                "The Issue remains open for maintainer review; Genesis will not create an unbounded chain of capability Issues."
            ),
        )
        return {"status": "needs_human", "issue_number": number, "reason": reason}

    capability = ensure_capability_issue(repository, token, issue, target, reason)
    capability_number = int(capability.get("number") or 0)

    # A previously created capability dependency may already be verified.
    # Never recreate a waiting loop around a satisfied dependency.
    if capability_number and capability_ready(repository, token, capability_number):
        refreshed = _release_waiting_issue(
            repository,
            token,
            issue,
            comments,
            capability_number,
        )
        return {
            "status": "capability_already_ready",
            "issue_number": number,
            "capability_issue": capability_number,
            "reason": reason,
            "released": True,
        }

    ensure_label(
        repository,
        token,
        WAITING_CAPABILITY_LABEL,
        "fbca04",
        "Parent Issue is open but paused until a linked Genesis capability is verified",
    )
    request(
        repository,
        token,
        "POST",
        f"/issues/{number}/labels",
        {"labels": [WAITING_CAPABILITY_LABEL, EXHAUSTED_LABEL, AGENTIC_LABEL]},
    )
    for label in ("genesis-repair-in-progress", "genesis-validating", "genesis-autonomous", "genesis-deferred"):
        remove_label(repository, token, number, label)

    marker = f"{CAPABILITY_DEPENDENCY_PREFIX}{capability_number} -->"
    _post_once(
        repository,
        token,
        number,
        comments,
        marker,
        (
            f"{marker}\n"
            f"Genesis identified a repair-capability dependency after trying materially different methods. Parent Issue #{number} stays open but is paused. "
            f"Capability Issue #{capability_number} must be verified before this Issue resumes. Blocker: `{reason or 'strategy_set_exhausted'}`."
        ),
    )

    capability_comments = issue_comments(repository, token, capability_number)
    parent_marker = f"<!-- genesis-capability-parent:{number} -->"
    _post_once(
        repository,
        token,
        capability_number,
        capability_comments,
        parent_marker,
        (
            f"{parent_marker}\n"
            f"Shared capability dependency also blocks parent Issue #{number}. The parent remains independently paused and will be released when this capability is verified/completed."
        ),
    )

    try:
        request(
            repository,
            token,
            "POST",
            "/actions/workflows/genesis-agentic-lab-recovery.yml/dispatches",
            {"ref": "main"},
        )
    except Exception:
        pass

    return {
        "status": "waiting_capability",
        "issue_number": number,
        "capability_issue": capability_number,
        "reason": reason,
    }


def _release_waiting_issue(
    repository: str,
    token: str,
    issue: dict,
    comments: list[dict],
    dependency: int,
) -> list[dict]:
    number = int(issue.get("number") or 0)
    for label in (WAITING_CAPABILITY_LABEL, "genesis-blocked", "genesis-deferred", EXHAUSTED_LABEL, NEEDS_HUMAN_LABEL):
        remove_label(repository, token, number, label)
    request(
        repository,
        token,
        "POST",
        f"/issues/{number}/labels",
        {"labels": ["genesis-autonomous", AGENTIC_LABEL]},
    )
    marker = f"{CAPABILITY_RELEASE_PREFIX}{dependency} -->"
    _post_once(
        repository,
        token,
        number,
        comments,
        marker,
        (
            f"{marker}\n"
            f"Capability Issue #{dependency} is verified/completed. Genesis is releasing this parent Issue for a fresh Agentic Lab strategy cycle using the new capability state."
        ),
    )
    return issue_comments(repository, token, number)


def release_ready_capability_dependencies(repository: str, token: str) -> list[int]:
    released: list[int] = []
    for issue in _all_issues(repository, token):
        if str(issue.get("state") or "").lower() != "open":
            continue
        issue_labels = labels(issue)
        if WAITING_CAPABILITY_LABEL not in issue_labels:
            continue
        number = int(issue.get("number") or 0)
        if number <= 0:
            continue
        comments = issue_comments(repository, token, number)
        dependency = unresolved_capability_dependency(comments)
        if not dependency or not capability_ready(repository, token, dependency):
            continue
        _release_waiting_issue(repository, token, issue, comments, dependency)
        released.append(number)
    return released


def reserve_and_dispatch(repository: str, token: str) -> dict:
    for issue in open_agentic_issues(repository, token):
        if str(issue.get("state") or "").lower() == "closed":
            continue

        issue_labels = labels(issue)
        if "genesis-verified" in issue_labels:
            continue

        number = int(issue.get("number") or 0)
        if number <= 0:
            continue

        comments = issue_comments(repository, token, number)
        lifecycle_block = local_claim_block_reason(issue, comments)
        if lifecycle_block:
            for stale_label in (
                "genesis-repair-in-progress",
                "genesis-validating",
                "genesis-autonomous",
                "genesis-deferred",
                "genesis-blocked",
                EXHAUSTED_LABEL,
                NEEDS_HUMAN_LABEL,
                AGENTIC_LABEL,
            ):
                remove_label(repository, token, number, stale_label)
            continue

        dependency = unresolved_capability_dependency(comments)
        if dependency:
            if not capability_ready(repository, token, dependency):
                continue
            comments = _release_waiting_issue(repository, token, issue, comments, dependency)
            issue_labels -= {WAITING_CAPABILITY_LABEL, "genesis-blocked", "genesis-deferred", EXHAUSTED_LABEL, NEEDS_HUMAN_LABEL}
            issue_labels |= {"genesis-autonomous", AGENTIC_LABEL}
        elif WAITING_CAPABILITY_LABEL in issue_labels:
            continue

        if issue_labels & ACTIVE_LABELS:
            continue

        target = explicit_target(str(issue.get("body") or ""))
        lane = safe_lane(target)
        if not lane:
            continue

        # Agentic Lab owns integration-sensitive classification and guidance.
        # Legacy integration workflow is now only a manual compatibility wake-up.
        apply_integration_route(repository, token, issue, target)

        state_token, comments = ensure_anti_stuck_epoch(
            repository, token, issue, comments, target
        )
        history = attempt_history(comments, state_token, target)
        policy = anti_stuck_decision(history)
        status = latest_result_status(comments, state_token)

        if status == "blocked_protected_or_unsupported_target":
            for label in ACTIVE_LABELS | {EXHAUSTED_LABEL, "genesis-blocked", "genesis-deferred"}:
                remove_label(repository, token, number, label)
            ensure_label(
                repository,
                token,
                "genesis-needs-routing",
                "fbca04",
                "Genesis needs a safer implementation target before autonomous repair can continue",
            )
            request(
                repository,
                token,
                "POST",
                f"/issues/{number}/labels",
                {"labels": ["genesis-needs-routing", AGENTIC_LABEL, "genesis-autonomous"]},
            )
            _post_once(
                repository,
                token,
                number,
                comments,
                "<!-- genesis-policy-block-rerouted -->",
                (
                    "<!-- genesis-policy-block-rerouted -->\n"
                    f"Genesis classified target `{target}` as protected/unsupported for the current repair lane. "
                    "This is a routing/policy condition, not a reusable capability gap. The Issue remains open and "
                    "is removed from autonomous repair until a safer target is derived."
                ),
            )
            continue

        if capability_gap_status(status) or policy.action == "capability":
            result = pause_for_capability(
                repository,
                token,
                issue,
                comments,
                target,
                status or policy.reason,
            )
            print(json.dumps(result, sort_keys=True))
            return result

        provider = "agentic-default"
        gene = "Gene 0"
        workflow = "genesis-agentic-strategy-worker.yml"

        if policy.action == "switch_lane" and policy.provider == "qwen3":
            provider = "qwen3"
            strategy = "qwen3_fallback"
        elif policy.action == "switch_lane" and policy.provider == "deepseek":
            provider = "deepseek"
            gene = "Gene 003"
            workflow = "genesis-deepseek-agentic-solver.yml"
            strategy = next_lane_strategy(
                history,
                provider=provider,
                gene=gene,
                target=target,
                strategies=("evidence_first", "alternative_implementation", "diagnostic_reframe"),
            ) or "evidence_first"
        else:
            strategy = next_lane_strategy(
                history,
                provider=provider,
                gene=gene,
                target=target,
                strategies=STRATEGIES,
            )

        if not strategy:
            result = pause_for_capability(
                repository,
                token,
                issue,
                comments,
                target,
                "strategy_set_exhausted",
            )
            print(json.dumps(result, sort_keys=True))
            return result

        candidate = Attempt(
            strategy=strategy,
            provider=provider,
            gene=gene,
            target=target,
            blocker=status,
        )
        if materially_equivalent_attempt(history, candidate):
            # Reject duplicate work before it consumes a repair slot and let the
            # loop consider another eligible Issue.
            continue

        ensure_label(
            repository,
            token,
            AGENTIC_LABEL,
            "8250df",
            "Normal bounded solver exhausted; Agentic Lab owns materially different recovery strategies for this open Issue",
        )
        for label in ("genesis-deferred", "genesis-blocked", EXHAUSTED_LABEL, NEEDS_HUMAN_LABEL):
            remove_label(repository, token, number, label)
        claim_labels = ["genesis-autonomous", AGENTIC_LABEL]
        if provider != "deepseek":
            claim_labels.insert(0, "genesis-repair-in-progress")
        request(
            repository,
            token,
            "POST",
            f"/issues/{number}/labels",
            {"labels": claim_labels},
        )

        if not has_state_marker(comments, state_token):
            request(
                repository,
                token,
                "POST",
                f"/issues/{number}/comments",
                {
                    "body": (
                        f"{state_marker(state_token)}\n"
                        "Genesis Anti-Stuck Controller established the initial material-state epoch "
                        "after preserving prior lane-local attempt history."
                    )
                },
            )

        strategy_marker = f"{STRATEGY_MARKER_PREFIX}{strategy} -->"
        if provider == "deepseek":
            comment_body = (
                "<!-- genesis-anti-stuck-lane-switch:deepseek -->\n"
                f"Genesis Anti-Stuck Controller is switching Issue #{number} to provider `deepseek` "
                f"through supporting Gene `Gene 003` for state epoch `{state_token}`. "
                "The DeepSeek lane records its own concrete attempt only after it accepts the reservation, "
                "so a failed handoff does not consume an attempt."
            )
        else:
            comment_body = (
                f"{attempt_marker(candidate)}\n"
                f"{strategy_marker}\n"
                f"Genesis Anti-Stuck Controller selected provider `{provider}`, supporting Gene `{gene}`, "
                f"and materially different strategy `{strategy}` for state epoch `{state_token}`. "
                "Prior failure evidence remains attached to this same authoritative Issue. "
                "Validation, protected-file, signing, secret, exact-promotion, and owner-control boundaries remain mandatory."
            )
        request(
            repository,
            token,
            "POST",
            f"/issues/{number}/comments",
            {"body": comment_body},
        )

        dispatch_path = (
            "/actions/workflows/genesis-deepseek-agentic-solver.yml/dispatches"
            if workflow == "genesis-deepseek-agentic-solver.yml"
            else "/actions/workflows/genesis-agentic-strategy-worker.yml/dispatches"
        )
        dispatch_inputs = {"issue_number": str(number)}
        if workflow == "genesis-agentic-strategy-worker.yml":
            dispatch_inputs["strategy"] = strategy

        try:
            request(
                repository,
                token,
                "POST",
                dispatch_path,
                {"ref": "main", "inputs": dispatch_inputs},
            )
        except Exception:
            remove_label(repository, token, number, "genesis-repair-in-progress")
            remove_label(repository, token, number, "genesis-autonomous")
            request(repository, token, "POST", f"/issues/{number}/labels", {"labels": [EXHAUSTED_LABEL, AGENTIC_LABEL]})
            raise

        result = {
            "status": "dispatched",
            "issue_number": number,
            "target": target,
            "lane": lane,
            "strategy": strategy,
            "provider": provider,
            "gene": gene,
            "state_token": state_token,
            "workflow": workflow,
        }
        print(json.dumps(result, sort_keys=True))
        return result

    result = {"status": "idle", "reason": "no_safely_routable_agentic_issue"}
    print(json.dumps(result, sort_keys=True))
    return result


def main() -> int:
    repository = os.environ.get("GITHUB_REPOSITORY", "").strip()
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if not repository or not token:
        raise RuntimeError("GITHUB_REPOSITORY and GITHUB_TOKEN are required")
    reserve_and_dispatch(repository, token)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())