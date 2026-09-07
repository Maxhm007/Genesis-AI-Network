from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import urllib.error
import urllib.parse
import urllib.request


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


def explicit_target(body: str) -> str:
    prefix = "- **Target:** `"
    for line in str(body or "").splitlines():
        if line.startswith(prefix) and "`" in line[len(prefix):]:
            return line[len(prefix):].split("`", 1)[0].strip()
    return ""


def safe_lane(target: str) -> str:
    if not target or ".." in Path(target).parts or target in PROTECTED_TARGETS:
        return ""
    if not (ROOT / target).is_file():
        return ""
    if target.startswith("genesis/") and target.endswith(".py"):
        return "generic"
    if target.startswith("scripts/") and target.endswith(".py"):
        return "specialist"
    return ""


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
        rows.extend(row for row in batch if isinstance(row, dict) and not row.get("pull_request"))
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


def _marker_number(text: str, prefix: str) -> int | None:
    match = re.search(re.escape(prefix) + r"(\d+)\s*-->", str(text or ""))
    return int(match.group(1)) if match else None


def capability_dependency_number(comments: list[dict]) -> int | None:
    for row in reversed(comments):
        number = _marker_number(str(row.get("body") or ""), CAPABILITY_DEPENDENCY_PREFIX)
        if number:
            return number
    return None


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


def latest_result_status(comments: list[dict]) -> str:
    for row in reversed(comments):
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
        "blocked_protected_or_unsupported_target",
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


def _capability_fingerprint(issue_number: int, target: str) -> str:
    raw = f"agentic-capability:{int(issue_number)}:{target}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:16]


def ensure_capability_issue(
    repository: str,
    token: str,
    issue: dict,
    target: str,
    reason: str,
) -> dict:
    parent_number = int(issue.get("number") or 0)
    fingerprint = _capability_fingerprint(parent_number, target)
    marker = f"{CAPABILITY_WORK_PREFIX}{fingerprint} -->"

    for row in _all_issues(repository, token):
        if marker in str(row.get("body") or ""):
            return row

    ensure_label(
        repository,
        token,
        CAPABILITY_GAP_LABEL,
        "5319e7",
        "Genesis capability work required before a blocked parent Issue can resume",
    )

    title = f"[Genesis Capability] Add repair capability required by #{parent_number}"
    body = (
        f"{marker}\n"
        f"<!-- genesis-capability-parent:{parent_number} -->\n"
        "This capability Issue was created automatically because materially different Agentic Lab repair strategies could not safely complete the parent Issue with current Genesis capabilities.\n\n"
        f"- **Parent issue:** #{parent_number}\n"
        f"- **Blocked target:** `{target}`\n"
        f"- **Observed blocker:** `{reason or 'strategy_set_exhausted'}`\n"
        "- **Task type:** `capability_growth`\n"
        "- **Target:** `genesis/github_issue_capability_builder.py`\n\n"
        "### Objective\n"
        "Add the smallest reusable Genesis repair capability that addresses this blocker class without hard-coding the parent Issue. The capability may improve evidence interpretation, repair-plan generation, provider/tool routing, or safe context selection as justified by repository evidence.\n\n"
        "### Acceptance\n"
        "- Capability is reusable for the blocker class, not specific to one Issue number.\n"
        "- Existing tests, Security, protected-file boundaries, signing, validation, exact promotion, secret boundaries, and owner control remain unchanged or stronger.\n"
        "- Add focused regression coverage for the new repair capability.\n"
        "- Close this Issue only after the capability is verified and promoted.\n\n"
        "### Dependency rule\n"
        f"Parent Issue #{parent_number} remains open but paused. Once this capability Issue is verified/completed, Agentic Lab may automatically resume the parent with a fresh strategy cycle.\n"
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

    try:
        request(
            repository,
            token,
            "POST",
            "/actions/workflows/genesis-sequential-issue-controller.yml/dispatches",
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
    marker = f"{CAPABILITY_RELEASE_PREFIX}{dependency} -->"
    request(
        repository,
        token,
        "POST",
        f"/issues/{number}/comments",
        {
            "body": (
                f"{marker}\n"
                f"Capability Issue #{dependency} is verified/completed. Genesis is releasing this parent Issue for a fresh Agentic Lab strategy cycle using the new capability state."
            )
        },
    )
    return issue_comments(repository, token, number)


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
        if WAITING_CAPABILITY_LABEL in issue_labels:
            dependency = capability_dependency_number(comments)
            if not dependency or not capability_ready(repository, token, dependency):
                continue
            comments = _release_waiting_issue(repository, token, issue, comments, dependency)
            issue_labels -= {WAITING_CAPABILITY_LABEL, "genesis-blocked", "genesis-deferred", EXHAUSTED_LABEL, NEEDS_HUMAN_LABEL}

        if issue_labels & ACTIVE_LABELS:
            continue

        target = explicit_target(str(issue.get("body") or ""))
        lane = safe_lane(target)
        if not lane:
            continue

        status = latest_result_status(comments)
        strategy = next_strategy(comments)
        if capability_gap_status(status) or not strategy:
            result = pause_for_capability(
                repository,
                token,
                issue,
                comments,
                target,
                status or "strategy_set_exhausted",
            )
            print(json.dumps(result, sort_keys=True))
            return result

        ensure_label(
            repository,
            token,
            AGENTIC_LABEL,
            "8250df",
            "Normal bounded solver exhausted; Agentic Lab owns materially different recovery strategies for this open Issue",
        )
        for label in ("genesis-deferred", "genesis-blocked", EXHAUSTED_LABEL, NEEDS_HUMAN_LABEL):
            remove_label(repository, token, number, label)
        request(
            repository,
            token,
            "POST",
            f"/issues/{number}/labels",
            {"labels": ["genesis-repair-in-progress", "genesis-autonomous", AGENTIC_LABEL]},
        )

        strategy_marker = f"{STRATEGY_MARKER_PREFIX}{strategy} -->"
        request(
            repository,
            token,
            "POST",
            f"/issues/{number}/comments",
            {
                "body": (
                    f"{strategy_marker}\n"
                    f"Agentic Lab is trying a materially different recovery method: `{strategy}`. "
                    "Prior failure evidence remains attached to this same authoritative Issue. The Issue stays open unless a verified repair is promoted. "
                    "All existing tests, Security, protected-file, signing, secret, validation, exact-promotion, and owner-control boundaries remain mandatory."
                )
            },
        )

        try:
            request(
                repository,
                token,
                "POST",
                "/actions/workflows/genesis-agentic-strategy-worker.yml/dispatches",
                {"ref": "main", "inputs": {"issue_number": str(number), "strategy": strategy}},
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
            "workflow": "genesis-agentic-strategy-worker.yml",
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
