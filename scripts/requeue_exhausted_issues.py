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
RUNTIME = ROOT / "runtime"
EVIDENCE_PATH = RUNTIME / "exhausted_issue_requeue.json"
ENGINE_PATHS = (
    "genesis/coding.py",
    "genesis/compact_edit_budget.py",
    ".github/workflows/genesis-bounded-repair-worker.yml",
    ".github/workflows/genesis-sequential-issue-controller.yml",
    "scripts/github_issue_autorepair.py",
    "scripts/requeue_exhausted_issues.py",
    "genesis/github_issue_capability_builder.py",
    "genesis/github_issue_cleanup.py",
    "genesis/learned_capabilities.py",
)
ACTIVE_LABELS = {
    "genesis-claimed",
    "genesis-working",
    "genesis-verifying",
    "genesis-repair-in-progress",
    "genesis-validating",
    "genesis-priority-claim",
}
EXHAUSTED_LABELS = {"genesis-solver-exhausted", "genesis-priority-exhausted"}
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
}
MEASUREMENT_PHRASES = (
    "post-promotion benchmark",
    "post-promotion remeasurement",
    "benchmark re-measurement",
    "benchmark remeasurement",
    "measured score improves",
    "same comparable benchmark",
)
TARGET_RE = re.compile(r"^- \*\*Target:\*\* `([^`]+)`", re.MULTILINE)
OLD_ATTEMPT_RE = re.compile(r"<!-- genesis-solver-attempt:(\d+) -->")
PRIORITY_ATTEMPT_RE = re.compile(r"<!-- genesis-priority-solver-attempt:(\d+) -->")
ATTEMPT_DISPLAY_RE = re.compile(r"Attempt: \*\*(\d+)/(\d+)\*\*")
SUCCESSOR_PARENT_RE = re.compile(r"<!-- genesis-unsolved-successor-of:(\d+) -->")
PRE_REPAIR_FAILURE_PHRASE = "repair status: `worker_failed_before_evidence`"
HANDOFF_COMMENT_MARKER = "<!-- genesis-unsolved-handoff -->"
REQUEUE_MARKER_PREFIX = "<!-- genesis-requeue-engine:"


def engine_generation(root: Path = ROOT) -> str:
    digest = hashlib.sha256()
    for relative in ENGINE_PATHS:
        path = root / relative
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()[:20]


def issue_labels(issue: dict) -> set[str]:
    result: set[str] = set()
    for row in issue.get("labels") or []:
        if isinstance(row, dict):
            name = str(row.get("name") or "").strip()
        else:
            name = str(row or "").strip()
        if name:
            result.add(name)
    return result


def _eligible_retry_target(issue: dict, root: Path) -> tuple[bool, str]:
    labels = issue_labels(issue)
    if labels & ACTIVE_LABELS:
        return False, "active"
    if "genesis-superseded" in labels:
        return False, "superseded"

    title = str(issue.get("title") or "").strip()
    body = str(issue.get("body") or "")
    lower_title = title.lower()
    lower_body = body.lower()

    if lower_title.startswith(("genesis chat:", "[genesis hourly report]", "[genesis gene chat]")):
        return False, "persistent_channel"
    if "persistent github-native reporting channel" in lower_body:
        return False, "persistent_channel"
    if "external-authority / independent-secret provisioning blocker" in lower_body:
        return False, "external_authority"
    if lower_title.startswith(("[genesis escalation] ai capability below target", "[genesis ops] ai capability below target")):
        return False, "umbrella_state"

    match = TARGET_RE.search(body)
    target = match.group(1).strip() if match else ""
    if not target.startswith("genesis/") or not target.endswith(".py") or ".." in target:
        return False, "no_safe_target"
    if target in PROTECTED_TARGETS:
        return False, "protected_target"
    if not (root / target).is_file():
        return False, "missing_target"
    return True, target


def eligible_exhausted_issue(issue: dict, root: Path = ROOT) -> tuple[bool, str]:
    if not issue_labels(issue) & EXHAUSTED_LABELS:
        return False, "not_exhausted"
    return _eligible_retry_target(issue, root)


def reset_attempt_status(body: str) -> str:
    body = OLD_ATTEMPT_RE.sub("<!-- genesis-solver-attempt:0 -->", str(body or ""), count=1)
    body = PRIORITY_ATTEMPT_RE.sub("<!-- genesis-priority-solver-attempt:0 -->", body, count=1)
    return body


def rollback_attempt_status(body: str) -> str:
    text = str(body or "")
    rolled_from: int | None = None

    def rollback_old(match: re.Match[str]) -> str:
        nonlocal rolled_from
        rolled_from = int(match.group(1))
        return f"<!-- genesis-solver-attempt:{max(0, rolled_from - 1)} -->"

    text = OLD_ATTEMPT_RE.sub(rollback_old, text, count=1)
    if rolled_from is None:
        def rollback_priority(match: re.Match[str]) -> str:
            nonlocal rolled_from
            rolled_from = int(match.group(1))
            return f"<!-- genesis-priority-solver-attempt:{max(0, rolled_from - 1)} -->"

        text = PRIORITY_ATTEMPT_RE.sub(rollback_priority, text, count=1)

    if rolled_from is not None:
        rolled_to = max(0, rolled_from - 1)

        def rollback_display(match: re.Match[str]) -> str:
            if int(match.group(1)) != rolled_from:
                return match.group(0)
            return f"Attempt: **{rolled_to}/{match.group(2)}**"

        text = ATTEMPT_DISPLAY_RE.sub(rollback_display, text, count=1)
    return text


def pre_repair_failure_after_marker(comments: list[dict], marker: str) -> bool:
    marker_index = -1
    failure_index = -1
    for index, row in enumerate(comments):
        if not isinstance(row, dict):
            continue
        body = str(row.get("body") or "")
        if body.startswith(marker):
            marker_index = index
        if PRE_REPAIR_FAILURE_PHRASE in body:
            failure_index = index
    return failure_index > marker_index


def successor_marker(parent_number: int) -> str:
    return f"<!-- genesis-unsolved-successor-of:{int(parent_number)} -->"


def is_successor_issue(issue: dict) -> bool:
    return bool(SUCCESSOR_PARENT_RE.search(str(issue.get("body") or "")))


def find_existing_successor(issues: list[dict], parent_number: int) -> dict | None:
    marker = successor_marker(parent_number)
    for issue in issues:
        if marker in str(issue.get("body") or ""):
            return issue
    return None


def latest_failure_summary(comments: list[dict]) -> str:
    preferred = (
        "Genesis bounded repair did not promote a verified change",
        "bounded attempt exhausted",
        "repair status:",
        "worker failed before repair evidence",
    )
    for row in reversed(comments):
        if not isinstance(row, dict):
            continue
        body = str(row.get("body") or "").strip()
        if body and any(phrase.lower() in body.lower() for phrase in preferred):
            return body[:1800]
    for row in reversed(comments):
        if isinstance(row, dict) and str(row.get("body") or "").strip():
            return str(row.get("body") or "").strip()[:1800]
    return "No detailed worker evidence was available; the bounded solver reached terminal exhaustion without verified promotion."


def build_successor_body(issue: dict, generation: str, failure_summary: str) -> str:
    number = int(issue.get("number") or 0)
    title = str(issue.get("title") or "").strip()
    body = str(issue.get("body") or "")
    target_match = TARGET_RE.search(body)
    target = target_match.group(1).strip() if target_match else ""
    target_line = f"- **Target:** `{target}`\n" if target else ""
    return (
        f"{successor_marker(number)}\n"
        f"<!-- genesis-unsolved-root:{number} -->\n"
        "This GitHub Issue is the new authoritative work item created because the parent Issue exhausted the current bounded repair strategy without verified completion.\n\n"
        f"- **Parent issue:** #{number}\n"
        f"- **Parent title:** {title}\n"
        f"- **Task type:** `repair_followup`\n"
        f"- **Repair-engine generation:** `{generation}`\n"
        f"{target_line}\n"
        "### Why the parent was not solved\n"
        f"{failure_summary}\n\n"
        "### Required next strategy\n"
        "Do not repeat the same failed implementation/proposal unchanged. Diagnose the blocker from the parent evidence first, then use a materially different bounded strategy. If the blocker is repair-engine/provider/tooling behavior, improve or route around that limitation before retrying the original objective. If it is target logic, implement the smallest alternative correction supported by current repository evidence.\n\n"
        "### Acceptance\n"
        "Complete the parent objective with verifiable evidence. Existing tests, Security, independent validation, protected-file boundaries, signing boundaries, secret boundaries, owner control, and exact promotion requirements remain mandatory.\n\n"
        "### Authority rule\n"
        "This successor replaces the parent as the active GitHub Issue for this repair generation. The Sequential Issue Controller remains the only solve/verify/close lane. The closed parent must not be reopened while this successor is authoritative.\n"
    )


def _successor_title(issue: dict) -> str:
    number = int(issue.get("number") or 0)
    title = str(issue.get("title") or "").strip()
    prefix = f"[Genesis Repair Follow-up] #{number} — "
    return (prefix + title)[:240]


def _request(repository: str, token: str, method: str, path: str, payload: dict | None = None):
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        f"https://api.github.com/repos/{repository}{path}",
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "Content-Type": "application/json",
            "User-Agent": "Genesis-AI-Network/exhausted-issue-requeue",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = response.read().decode("utf-8")
        return json.loads(raw) if raw.strip() else {}
    except urllib.error.HTTPError as exc:
        if method == "DELETE" and exc.code == 404:
            return {}
        detail = exc.read().decode("utf-8", errors="replace")[:1000]
        raise RuntimeError(f"GitHub HTTP {exc.code} for {method} {path}: {detail}") from exc


def _ensure_label(repository: str, token: str, name: str, color: str, description: str) -> None:
    try:
        _request(repository, token, "POST", "/labels", {"name": name, "color": color, "description": description})
    except RuntimeError as exc:
        if "HTTP 422" not in str(exc):
            raise


def _open_issues(repository: str, token: str) -> list[dict]:
    rows: list[dict] = []
    for page in range(1, 101):
        batch = _request(repository, token, "GET", f"/issues?state=all&sort=created&direction=asc&per_page=100&page={page}")
        if not isinstance(batch, list):
            raise RuntimeError("GitHub open-Issue response was not a list")
        rows.extend(row for row in batch if isinstance(row, dict) and not row.get("pull_request"))
        if len(batch) < 100:
            break
    return rows


def create_successor_handoff(
    repository: str,
    token: str,
    issue: dict,
    issues: list[dict],
    generation: str,
    comments: list[dict],
) -> dict:
    number = int(issue.get("number") or 0)
    if number <= 0:
        raise RuntimeError("terminal handoff requires a valid parent issue number")
    if is_successor_issue(issue):
        raise RuntimeError("successor issues are held for a future repair-engine generation instead of creating an unbounded successor chain")

    existing = find_existing_successor(issues, number)
    if existing is None:
        _ensure_label(repository, token, "genesis-repair", "b60205", "Concrete repair work prioritized by the Genesis Sequential Issue Controller")
        created = _request(
            repository,
            token,
            "POST",
            "/issues",
            {
                "title": _successor_title(issue),
                "body": build_successor_body(issue, generation, latest_failure_summary(comments)),
                "labels": ["genesis-task", "genesis-autonomous", "genesis-repair"],
            },
        )
        if not isinstance(created, dict) or not int(created.get("number") or 0):
            raise RuntimeError("GitHub did not return a valid successor issue")
        successor = created
    else:
        successor = existing

    successor_number = int(successor.get("number") or 0)
    successor_url = str(successor.get("html_url") or successor.get("url") or f"https://github.com/{repository}/issues/{successor_number}")

    _ensure_label(repository, token, "genesis-superseded", "6e7781", "Closed because a linked successor Issue became the authoritative repair work item")
    _request(
        repository,
        token,
        "POST",
        f"/issues/{number}/labels",
        {"labels": ["genesis-blocked", "genesis-solver-exhausted", "genesis-deferred", "genesis-superseded"]},
    )
    encoded = urllib.parse.quote("genesis-autonomous", safe="")
    _request(repository, token, "DELETE", f"/issues/{number}/labels/{encoded}")

    if not any(HANDOFF_COMMENT_MARKER in str(row.get("body") or "") for row in comments if isinstance(row, dict)):
        _request(
            repository,
            token,
            "POST",
            f"/issues/{number}/comments",
            {
                "body": (
                    f"{HANDOFF_COMMENT_MARKER}\n"
                    "Genesis could not produce a verified solution within this bounded repair generation. "
                    f"The blocker/failure evidence has been carried into successor Issue #{successor_number}: {successor_url}. "
                    "This parent is now superseded and will remain closed so the queue has one authoritative work item instead of duplicate retries."
                )
            },
        )

    _request(repository, token, "PATCH", f"/issues/{number}", {"state": "closed", "state_reason": "not_planned"})
    return {"parent": number, "successor": successor_number, "successor_url": successor_url, "created": existing is None}


def run(repository: str, token: str, root: Path = ROOT, limit: int = 5) -> dict:
    generation = engine_generation(root)
    marker = f"<!-- genesis-requeue-engine:{generation} -->"
    issues = _open_issues(repository, token)
    result = {
        "status": "ok",
        "engine_generation": generation,
        "released": [],
        "successor_handoffs": [],
        "successor_handoff_failed": [],
        "successor_generation_holds": [],
        "infrastructure_quarantined": [],
        "skipped_same_generation": [],
        "skipped": [],
    }
    quarantined: set[int] = set()
    handed_off: set[int] = set()
    terminal_hold: set[int] = set()

    # Terminally deferred parents must not disappear as dead backlog. Create one
    # linked successor that carries the failure evidence and becomes the new
    # authoritative work item. Successors themselves do not form an unbounded
    # chain: after they exhaust, hold them for the current engine generation and
    # release that same successor only when the repair engine materially changes.
    handoff_count = 0
    for issue in issues:
        if handoff_count >= max(1, limit):
            break
        number = int(issue.get("number") or 0)
        labels = issue_labels(issue)
        if not (labels & EXHAUSTED_LABELS and "genesis-deferred" in labels):
            continue
        if "genesis-superseded" in labels:
            terminal_hold.add(number)
            continue

        comments = _request(repository, token, "GET", f"/issues/{number}/comments?per_page=100") or []
        if is_successor_issue(issue):
            engine_markers = [
                str(row.get("body") or "")
                for row in comments
                if isinstance(row, dict) and str(row.get("body") or "").startswith(REQUEUE_MARKER_PREFIX)
            ]
            if any(text.startswith(marker) for text in engine_markers):
                terminal_hold.add(number)
                result["successor_generation_holds"].append({"issue": number, "generation": generation})
                continue
            if not engine_markers:
                _request(
                    repository,
                    token,
                    "POST",
                    f"/issues/{number}/comments",
                    {
                        "body": (
                            marker
                            + "\nThis repair-follow-up Issue also exhausted the current bounded repair generation. "
                            + "Genesis will not create an unbounded chain of duplicate successor Issues. "
                            + "This same successor remains deferred until the repair-engine generation changes, when it may be released for one fresh bounded attempt set."
                        )
                    },
                )
                terminal_hold.add(number)
                result["successor_generation_holds"].append({"issue": number, "generation": generation})
                continue
            # An older engine marker exists but the current one does not: the
            # repair engine changed, so normal generation-release logic below may
            # reopen this same successor without creating another successor.
            continue

        try:
            handoff = create_successor_handoff(repository, token, issue, issues, generation, comments)
        except Exception as exc:
            terminal_hold.add(number)
            result["successor_handoff_failed"].append({"issue": number, "error": str(exc)[:500]})
            continue
        handed_off.add(number)
        handoff_count += 1
        result["successor_handoffs"].append(handoff)

    # A worker that failed before repair evidence did not spend a coding attempt.
    # Roll that dispatch marker back and quarantine the issue for this exact engine
    # generation so successor wakeups cannot burn the remaining bounded attempts.
    for issue in issues:
        number = int(issue.get("number") or 0)
        labels = issue_labels(issue)
        if str(issue.get("state") or "open") != "open":
            continue
        if labels & (ACTIVE_LABELS | EXHAUSTED_LABELS):
            continue
        if "genesis-autonomous" not in labels:
            continue
        eligible, target = _eligible_retry_target(issue, root)
        if not eligible:
            continue
        comments = _request(repository, token, "GET", f"/issues/{number}/comments?per_page=100") or []
        if not pre_repair_failure_after_marker(comments, marker):
            continue

        for row in comments:
            if not isinstance(row, dict):
                continue
            body = str(row.get("body") or "")
            if body.startswith("<!-- genesis-oldest-real-issue-solver -->") or body.startswith("<!-- genesis-priority-issue-solver -->"):
                rolled_back = rollback_attempt_status(body)
                if rolled_back != body:
                    _request(repository, token, "PATCH", f"/issues/comments/{row['id']}", {"body": rolled_back})

        _request(
            repository,
            token,
            "POST",
            f"/issues/{number}/labels",
            {"labels": ["genesis-blocked", "genesis-solver-exhausted"]},
        )
        encoded = urllib.parse.quote("genesis-autonomous", safe="")
        _request(repository, token, "DELETE", f"/issues/{number}/labels/{encoded}")
        _request(
            repository,
            token,
            "POST",
            f"/issues/{number}/comments",
            {
                "body": (
                    marker
                    + "\nGenesis worker failed before repair evidence existed, so this dispatch did not consume a coding attempt. "
                    + "The issue is quarantined for this repair-engine generation to prevent successor wakeups from repeatedly spending infrastructure runs. "
                    + f"It can be released automatically after a repair capability change. Engine generation: `{generation}`. Target: `{target}`."
                )
            },
        )
        quarantined.add(number)
        result["infrastructure_quarantined"].append({"issue": number, "target": target})

    for issue in issues:
        if len(result["released"]) >= max(1, limit):
            break
        number = int(issue.get("number") or 0)
        if number in quarantined or number in handed_off or number in terminal_hold:
            continue
        labels = issue_labels(issue)
        eligible, reason = eligible_exhausted_issue(issue, root)
        if not eligible:
            if labels & EXHAUSTED_LABELS:
                result["skipped"].append({"issue": number, "reason": reason})
            continue

        comments = _request(repository, token, "GET", f"/issues/{number}/comments?per_page=100") or []
        if any(str(row.get("body") or "").startswith(marker) for row in comments if isinstance(row, dict)):
            result["skipped_same_generation"].append(number)
            continue

        for row in comments:
            if not isinstance(row, dict):
                continue
            body = str(row.get("body") or "")
            if body.startswith("<!-- genesis-oldest-real-issue-solver -->") or body.startswith("<!-- genesis-priority-issue-solver -->"):
                reset = reset_attempt_status(body)
                if reset != body:
                    _request(repository, token, "PATCH", f"/issues/comments/{row['id']}", {"body": reset})

        if str(issue.get("state") or "open") == "closed":
            reopened = _request(repository, token, "PATCH", f"/issues/{number}", {"state": "open"})
            if not isinstance(reopened, dict) or str(reopened.get("state") or "") != "open":
                result["skipped"].append({"issue": number, "reason": "reopen_failed"})
                continue

        for label in ("genesis-solver-exhausted", "genesis-priority-exhausted", "genesis-blocked", "genesis-deferred"):
            encoded = urllib.parse.quote(label, safe="")
            _request(repository, token, "DELETE", f"/issues/{number}/labels/{encoded}")

        _request(
            repository,
            token,
            "POST",
            f"/issues/{number}/comments",
            {
                "body": (
                    marker
                    + "\nGenesis repair capability changed. This previously exhausted Issue is released for one new bounded solver generation. "
                    + f"Engine generation: `{generation}`. Existing safety, target, validation and attempt limits remain unchanged."
                )
            },
        )
        result["released"].append({"issue": number, "target": reason})

    RUNTIME.mkdir(parents=True, exist_ok=True)
    EVIDENCE_PATH.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result


def main() -> None:
    repository = os.environ.get("GITHUB_REPOSITORY", "").strip()
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if not repository or not token:
        raise SystemExit("GITHUB_REPOSITORY and GITHUB_TOKEN are required")
    limit = int(os.environ.get("GENESIS_EXHAUSTED_REQUEUE_LIMIT", "5"))
    print(json.dumps(run(repository, token, limit=limit), indent=2, sort_keys=True))

    # The Sequential Controller invokes this script immediately before it
    # refreshes the open-Issue queue. Run the narrow verification-only detector
    # reconciler here so an already-fixed machine regression cannot race ahead
    # into a bounded repair reservation. Other requeue entrypoints keep their
    # existing behavior unchanged.
    if os.environ.get("GITHUB_WORKFLOW", "").strip() == "Genesis Sequential Issue Controller":
        from genesis.github_issue_detected_reconciler import reconcile_satisfied_detected_issues

        detected = reconcile_satisfied_detected_issues(ROOT)
        print("Satisfied detected regression controller preflight:")
        print(json.dumps(detected, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
