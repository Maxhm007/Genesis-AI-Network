from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import re

import agentic_lab_recovery_dispatch as agentic


STALE_RESERVATION_MINUTES = 100
SAME_ISSUE_MEMORY_PREFIX = "<!-- genesis-same-issue-recovery-memory:"
LEGACY_DEPENDENCY_RELEASE = "<!-- genesis-legacy-capability-dependency-released -->"
FIFO_DECOMPOSITION_PREFIX = "<!-- genesis-fifo-decomposition:"
FIFO_BLOCKED_MARKER = "<!-- genesis-fifo-decomposition-blocked -->"


def _all_issue_comments(repository: str, token: str, number: int) -> list[dict]:
    rows: list[dict] = []
    for page in range(1, 101):
        batch = agentic.request(repository, token, "GET", f"/issues/{number}/comments?per_page=100&page={page}") or []
        if not isinstance(batch, list):
            raise RuntimeError("GitHub issue comments response was not a list")
        rows.extend(row for row in batch if isinstance(row, dict))
        if len(batch) < 100:
            break
    return rows


def _all_open_issues_fifo(repository: str, token: str) -> list[dict]:
    rows: list[dict] = []
    for page in range(1, 101):
        batch = agentic.request(repository, token, "GET", f"/issues?state=open&sort=created&direction=asc&per_page=100&page={page}") or []
        if not isinstance(batch, list):
            raise RuntimeError("GitHub open issue response was not a list")
        rows.extend(row for row in batch if isinstance(row, dict) and not row.get("pull_request"))
        if len(batch) < 100:
            break
    return rows


def _actionable(issue: dict) -> bool:
    issue_labels = agentic.labels(issue)
    autonomous_or_agentic = "genesis-autonomous" in issue_labels or agentic.AGENTIC_LABEL in issue_labels
    if not autonomous_or_agentic or "genesis-verified" in issue_labels:
        return False
    if issue_labels & {"genesis-persistent", "duplicate", "invalid", "wontfix", "genesis-superseded"}:
        return False
    number = int(issue.get("number") or 0)
    title = str(issue.get("title") or "").strip().lower()
    body = str(issue.get("body") or "")
    if number <= 1:
        return False
    if title.startswith(("[genesis gene chat]", "genesis chat:", "[genesis hourly report]", "[genesis ops]")):
        return False
    if "persistent github-native reporting channel" in body.lower():
        return False
    return True


def _restore_agentic_visibility(repository: str, token: str, issues: list[dict]) -> list[int]:
    restored: list[int] = []
    for issue in issues:
        labels = agentic.labels(issue)
        if agentic.AGENTIC_LABEL not in labels or "genesis-autonomous" in labels:
            continue
        if "genesis-verified" in labels or "genesis-superseded" in labels:
            continue
        number = int(issue.get("number") or 0)
        if number <= 1:
            continue
        title = str(issue.get("title") or "").strip().lower()
        body = str(issue.get("body") or "").lower()
        if title.startswith(("[genesis gene chat]", "genesis chat:", "[genesis hourly report]", "[genesis ops]")):
            continue
        if "persistent github-native reporting channel" in body:
            continue
        agentic.request(repository, token, "POST", f"/issues/{number}/labels", {"labels": ["genesis-autonomous"]})
        agentic.remove_label(repository, token, number, "genesis-deferred")
        restored.append(number)
    return restored


def _derived_safe_target(body: str) -> str:
    explicit = agentic.explicit_target(body)
    if agentic.safe_lane(explicit):
        return explicit

    owner = re.search(r"^- \*\*Owning module:\*\* `([A-Za-z0-9_.]+)`", body, re.MULTILINE)
    if owner:
        module = owner.group(1).strip()
        if module.startswith("genesis."):
            candidate = module.replace(".", "/") + ".py"
            if agentic.safe_lane(candidate):
                return candidate

    candidates = re.findall(r"`((?:genesis|scripts)/[^`\n]+\.py)`", body)
    for candidate in candidates:
        normalized = candidate.strip().replace("\\", "/")
        if ".." in Path(normalized).parts:
            continue
        if agentic.safe_lane(normalized):
            return normalized
    return ""


def _decompose_oldest_issue(repository: str, token: str, issues: list[dict]) -> dict:
    for issue in issues:
        if not _actionable(issue):
            continue
        number = int(issue.get("number") or 0)
        body = str(issue.get("body") or "")
        explicit = agentic.explicit_target(body)
        if agentic.safe_lane(explicit):
            return {"status": "already_routable", "issue_number": number, "target": explicit}

        target = _derived_safe_target(body)
        comments = agentic.issue_comments(repository, token, number)
        if not target:
            if not any(FIFO_BLOCKED_MARKER in str(row.get("body") or "") for row in comments):
                agentic.request(repository, token, "POST", f"/issues/{number}/comments", {"body": (
                    f"{FIFO_BLOCKED_MARKER}\n"
                    "**Genesis FIFO decomposition blocked**\n\n"
                    "This is the oldest actionable autonomous Issue, so Genesis will not let newer work jump ahead. "
                    "No existing safe single-file target can be derived from the Issue metadata or referenced repository paths. "
                    "Genesis must extend same-Issue repair support for new-file or multi-file work before this Issue can advance. "
                    "No child/successor/capability Issue was created."
                )})
            return {"status": "fifo_blocked", "issue_number": number, "reason": "no_safe_single_file_decomposition"}

        marker = f"{FIFO_DECOMPOSITION_PREFIX}{number} -->"
        if not any(marker in str(row.get("body") or "") for row in comments):
            new_body = body.rstrip() + (
                "\n\n### Genesis FIFO decomposition\n"
                f"- **Target:** `{target}`\n"
                "- **Authority:** This remains the same authoritative Issue; no child or successor Issue is created.\n"
                "- **Execution:** Complete the smallest verified step toward the original acceptance criteria, then continue on this same Issue if more work remains.\n"
            )
            agentic.request(repository, token, "PATCH", f"/issues/{number}", {"body": new_body})
            agentic.request(repository, token, "POST", f"/issues/{number}/comments", {"body": (
                f"{marker}\n"
                "**Genesis FIFO decomposition**\n\n"
                f"Derived safe first implementation target: `{target}`. "
                "The original Issue remains authoritative. Previous comments remain repair memory, and no additional Issue was created."
            )})
            for label in ("genesis-needs-routing", "genesis-blocked", "genesis-deferred", agentic.EXHAUSTED_LABEL):
                agentic.remove_label(repository, token, number, label)
            agentic.request(repository, token, "POST", f"/issues/{number}/labels", {"labels": [agentic.AGENTIC_LABEL, "genesis-autonomous"]})
        return {"status": "decomposed", "issue_number": number, "target": target}
    return {"status": "idle", "reason": "no_actionable_fifo_issue"}


def _fifo_autonomous_issues(repository: str, token: str) -> list[dict]:
    eligible: list[dict] = []
    for issue in _all_open_issues_fifo(repository, token):
        if not _actionable(issue):
            continue
        target = agentic.explicit_target(str(issue.get("body") or ""))
        if not agentic.safe_lane(target):
            break
        eligible.append(issue)
    print(json.dumps({"selector": "strict_fifo_autonomous", "eligible_fifo": [int(row.get("number") or 0) for row in eligible]}, sort_keys=True))
    return eligible


def _latest_strategy_time(comments: list[dict]) -> datetime | None:
    for row in reversed(comments):
        body = str(row.get("body") or "")
        if not body.startswith(agentic.STRATEGY_MARKER_PREFIX):
            continue
        raw = str(row.get("created_at") or "").strip()
        if not raw:
            return None
        try:
            return datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


def _least_recently_used_strategy(comments: list[dict]) -> str:
    last_seen = {strategy: -1 for strategy in agentic.STRATEGIES}
    release_index = agentic._latest_release_index(comments)
    for index, row in enumerate(comments[release_index + 1 :], start=release_index + 1):
        body = str(row.get("body") or "")
        if not body.startswith(agentic.STRATEGY_MARKER_PREFIX):
            continue
        strategy = body[len(agentic.STRATEGY_MARKER_PREFIX) :].split("-->", 1)[0].strip()
        if strategy in last_seen:
            last_seen[strategy] = index
    return min(agentic.STRATEGIES, key=lambda strategy: (last_seen[strategy], agentic.STRATEGIES.index(strategy)))


def _clear_stale_reservations(repository: str, token: str, issues: list[dict]) -> list[int]:
    stale: list[int] = []
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=STALE_RESERVATION_MINUTES)
    for issue in issues:
        issue_labels = agentic.labels(issue)
        if not (issue_labels & agentic.ACTIVE_LABELS):
            continue
        number = int(issue.get("number") or 0)
        comments = agentic.issue_comments(repository, token, number)
        last_strategy = _latest_strategy_time(comments)
        if last_strategy is None or last_strategy > cutoff:
            continue
        for label in agentic.ACTIVE_LABELS | {"genesis-recovery-solver"}:
            agentic.remove_label(repository, token, number, label)
        agentic.request(repository, token, "POST", f"/issues/{number}/labels", {"labels": [agentic.AGENTIC_LABEL, "genesis-autonomous"]})
        agentic.request(repository, token, "POST", f"/issues/{number}/comments", {"body": (
            "<!-- genesis-stale-agentic-reservation-released -->\n"
            f"Genesis released a stale repair reservation older than {STALE_RESERVATION_MINUTES} minutes. "
            "The same Issue remains authoritative; its existing failure comments remain repair memory for the next FIFO attempt."
        )})
        stale.append(number)
    return stale


def _release_legacy_waiting_dependencies(repository: str, token: str, issues: list[dict]) -> list[int]:
    released: list[int] = []
    for issue in issues:
        issue_labels = agentic.labels(issue)
        if agentic.WAITING_CAPABILITY_LABEL not in issue_labels:
            continue
        number = int(issue.get("number") or 0)
        comments = agentic.issue_comments(repository, token, number)
        for label in (agentic.WAITING_CAPABILITY_LABEL, "genesis-blocked", "genesis-deferred", agentic.EXHAUSTED_LABEL, agentic.NEEDS_HUMAN_LABEL):
            agentic.remove_label(repository, token, number, label)
        agentic.request(repository, token, "POST", f"/issues/{number}/labels", {"labels": [agentic.AGENTIC_LABEL, "genesis-autonomous"]})
        if not any(LEGACY_DEPENDENCY_RELEASE in str(row.get("body") or "") for row in comments):
            agentic.request(repository, token, "POST", f"/issues/{number}/comments", {"body": (
                f"{LEGACY_DEPENDENCY_RELEASE}\n"
                "Genesis no longer creates or waits on a secondary capability Issue merely because this Issue was not solved. "
                "This original Issue is authoritative again. Previous failure comments are retained as repair memory."
            )})
        released.append(number)
    return released


def _same_issue_pause(repository: str, token: str, issue: dict, comments: list[dict], target: str, reason: str) -> dict:
    number = int(issue.get("number") or 0)
    count = sum(1 for row in comments if str(row.get("body") or "").startswith(SAME_ISSUE_MEMORY_PREFIX)) + 1
    marker = f"{SAME_ISSUE_MEMORY_PREFIX}{count} -->"
    agentic.request(repository, token, "POST", f"/issues/{number}/comments", {"body": (
        f"{marker}\n"
        "**Genesis same-issue recovery memory**\n\n"
        f"- Target: `{target}`\n"
        f"- Latest blocker: `{reason or 'strategy_set_exhausted'}`\n"
        "- Decision: keep this Issue open and authoritative; do not create a successor or capability Issue.\n"
        "- Next attempt: read the full comment history and use the least-recently-used safe strategy."
    )})
    for label in agentic.ACTIVE_LABELS | {agentic.WAITING_CAPABILITY_LABEL, agentic.NEEDS_HUMAN_LABEL, "genesis-blocked", "genesis-deferred", "genesis-recovery-solver", agentic.EXHAUSTED_LABEL}:
        agentic.remove_label(repository, token, number, label)
    agentic.request(repository, token, "POST", f"/issues/{number}/labels", {"labels": [agentic.AGENTIC_LABEL, "genesis-autonomous"]})
    return {"status": "same_issue_retry", "issue_number": number, "reason": reason}


def main() -> int:
    repository = os.environ.get("GITHUB_REPOSITORY", "").strip()
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if not repository or not token:
        raise RuntimeError("GITHUB_REPOSITORY and GITHUB_TOKEN are required")

    agentic.issue_comments = _all_issue_comments
    agentic.open_agentic_issues = _fifo_autonomous_issues
    agentic.next_strategy = _least_recently_used_strategy
    agentic.capability_gap_status = lambda _status: False
    agentic.pause_for_capability = _same_issue_pause

    all_open = _all_open_issues_fifo(repository, token)
    restored = _restore_agentic_visibility(repository, token, all_open)
    all_open = _all_open_issues_fifo(repository, token)
    released = _release_legacy_waiting_dependencies(repository, token, all_open)
    decomposition = _decompose_oldest_issue(repository, token, _all_open_issues_fifo(repository, token))
    if decomposition.get("status") == "fifo_blocked":
        print(json.dumps({"status": "fifo_blocked", "decomposition": decomposition, "legacy_dependencies_released": released, "agentic_visibility_restored": restored}, sort_keys=True))
        return 0

    fifo = _fifo_autonomous_issues(repository, token)
    stale = _clear_stale_reservations(repository, token, fifo)
    if stale:
        fifo = _fifo_autonomous_issues(repository, token)

    active = [int(issue.get("number") or 0) for issue in _all_open_issues_fifo(repository, token) if agentic.labels(issue) & agentic.ACTIVE_LABELS]
    if active:
        print(json.dumps({"status": "busy", "reason": "global_fifo_repair_lock", "active_issues": active, "decomposition": decomposition, "agentic_visibility_restored": restored}, sort_keys=True))
        return 0

    result = agentic.reserve_and_dispatch(repository, token)
    if isinstance(result, dict):
        result["policy"] = "strict_fifo_same_issue_decomposition"
        result["decomposition"] = decomposition
        result["agentic_visibility_restored"] = restored
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
