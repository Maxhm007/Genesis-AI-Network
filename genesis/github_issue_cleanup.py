from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from pathlib import Path
from typing import Callable

from .github_issue_task_router import issue_authority_enabled


PROTECTED_LABELS = {"genesis-persistent", "genesis-control"}
PROTECTED_TITLE_PREFIXES = ("Genesis Control:",)
EXPLICIT_CLOSE_LABELS = {"duplicate", "invalid", "wontfix"}
MANAGED_MARKER_RE = re.compile(
    r"<!--\s*(genesis-ops|genesis-chatgpt-escalation):([A-Za-z0-9._-]+)\s*-->",
    re.IGNORECASE,
)
TARGET_RE = re.compile(r"^- \*\*Target:\*\* `([^`]+)`", re.MULTILINE)
PYTHON_PATH_RE = re.compile(r"(?<![A-Za-z0-9_./-])(genesis/[A-Za-z0-9_./-]+\.py)(?![A-Za-z0-9_/-]|\.[A-Za-z0-9_-])")
TASK_TYPE_RE = re.compile(r"^- \*\*Task type:\*\* `([^`]+)`", re.MULTILINE)
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
TASK_TYPE_TARGETS = {
    "benchmark_runner_integration": "genesis/benchmark_execution.py",
}
ROUTING_NOTE_HEADER = "### Genesis deterministic routing evidence"

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
            "User-Agent": "Genesis-AI-Network/github-issue-cleanup",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = response.read().decode("utf-8")
        return json.loads(raw) if raw.strip() else {}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        print(f"GitHub issue cleanup HTTP {exc.code}: {detail}")
        return None
    except Exception as exc:
        print(f"GitHub issue cleanup unavailable: {type(exc).__name__}: {exc}")
        return None


def _issue_labels(issue: dict) -> set[str]:
    labels: set[str] = set()
    for label in issue.get("labels") or []:
        if isinstance(label, dict):
            name = str(label.get("name") or "").strip().lower()
        else:
            name = str(label or "").strip().lower()
        if name:
            labels.add(name)
    return labels


def _protected_issue(issue: dict) -> bool:
    title = str(issue.get("title") or "").strip()
    if any(title.startswith(prefix) for prefix in PROTECTED_TITLE_PREFIXES):
        return True
    return bool(_issue_labels(issue) & PROTECTED_LABELS)


def _issue_number(issue: dict) -> int:
    try:
        return int(issue.get("number") or 0)
    except (TypeError, ValueError):
        return 0


def _managed_key(issue: dict) -> tuple[str, str] | None:
    body = str(issue.get("body") or "")
    match = MANAGED_MARKER_RE.search(body)
    if not match:
        return None
    return match.group(1).lower(), match.group(2).lower()


def _list_open_issues(requester: GithubRequester) -> list[dict] | None:
    issues: list[dict] = []
    for page in range(1, 101):
        response = requester("GET", f"/issues?state=open&per_page=100&page={page}", None)
        if not isinstance(response, list):
            return None
        batch = [
            dict(issue)
            for issue in response
            if isinstance(issue, dict)
            and str(issue.get("state") or "open") == "open"
            and "pull_request" not in issue
        ]
        issues.extend(batch)
        if len(response) < 100:
            break
    return issues


def _close_issue(
    requester: GithubRequester,
    issue: dict,
    *,
    reason: str,
    state_reason: str = "not_planned",
) -> dict | None:
    number = _issue_number(issue)
    if number <= 0:
        return None
    updated = requester(
        "PATCH",
        f"/issues/{number}",
        {"state": "closed", "state_reason": state_reason},
    )
    if not isinstance(updated, dict) or str(updated.get("state") or "") != "closed":
        return None
    return {
        "github_issue_number": number,
        "reason": reason,
        "state_reason": state_reason,
    }


def _safe_existing_target(root: Path, target: str) -> bool:
    candidate = str(target or "").strip().replace("\\", "/")
    if not candidate.startswith("genesis/") or not candidate.endswith(".py"):
        return False
    if ".." in candidate or candidate in PROTECTED_TARGETS:
        return False
    return (root / candidate).is_file()


def _task_type(body: str) -> str:
    match = TASK_TYPE_RE.search(str(body or ""))
    return match.group(1).strip() if match else ""


def _routing_target(issue: dict, root: Path) -> tuple[str, str] | None:
    """Return one conservative generic-code target when routing evidence is deterministic.

    Existing explicit targets are left untouched. Inference is restricted to ordinary
    ``[Genesis Task]`` records because repair/control/specialist issues can require
    multi-file or non-code handling even when a Python path appears in prose.
    """
    title = str(issue.get("title") or "").strip()
    body = str(issue.get("body") or "")
    labels = _issue_labels(issue)
    lower_title = title.lower()
    lower_body = body.lower()

    if TARGET_RE.search(body):
        return None
    if not title.startswith("[Genesis Task]"):
        return None
    if labels & {"genesis-solver-exhausted", "genesis-persistent", "genesis-control", "duplicate"}:
        return None
    if lower_title.startswith(("[genesis escalation]", "[genesis ops]")):
        return None
    if "external-authority / independent-secret provisioning blocker" in lower_body:
        return None
    if any(phrase in lower_body for phrase in MEASUREMENT_PHRASES):
        return None

    task_type = _task_type(body)
    mapped = TASK_TYPE_TARGETS.get(task_type, "")
    if mapped and _safe_existing_target(root, mapped):
        return mapped, f"task_type_map:{task_type}"

    candidates = sorted(set(PYTHON_PATH_RE.findall(body)))
    if len(candidates) != 1:
        return None
    candidate = candidates[0]
    if not _safe_existing_target(root, candidate):
        return None
    return candidate, "single_evidenced_python_path"


def _append_routing_target(body: str, target: str, reason: str) -> str:
    text = str(body or "").rstrip()
    note = (
        f"{ROUTING_NOTE_HEADER}\n"
        f"- **Target:** `{target}`\n"
        f"- **Routing basis:** `{reason}`\n\n"
        "Genesis added this target only because the issue already supplied deterministic bounded routing evidence. "
        "This does not waive tests, Security, protected-file rules, independent validation, or verified closure."
    )
    return f"{text}\n\n{note}\n" if text else f"{note}\n"


def cleanup_obsolete_github_issues(
    root: Path,
    *,
    requester: GithubRequester | None = None,
) -> dict:
    """Conservatively close obsolete records and route deterministically inferable tasks.

    Cleanup never treats age, title similarity, or a failed repair attempt as closure
    evidence. Routing never invents a target: it is limited to an explicit task-type
    mapping or exactly one safe current Python path already evidenced by an ordinary
    Genesis Task. Specialist, measurement, protected and exhausted work stays out of
    the generic repair lane.
    """
    root = Path(root).resolve()
    runtime = root / "runtime"
    runtime.mkdir(parents=True, exist_ok=True)
    report_path = runtime / "github_issue_cleanup.json"
    explicit_requester = requester is not None

    result = {
        "status": "ok",
        "enforced": bool(explicit_requester or issue_authority_enabled(root)),
        "scanned": 0,
        "closed": [],
        "routed": [],
        "kept_current": [],
        "skipped_protected": [],
        "blocked": [],
    }

    if not result["enforced"]:
        result["status"] = "not_repository_runtime"
        result["reason"] = "temporary/non-repository runtime; real GitHub Issue mutations are disabled"
        report_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return result

    requester = requester or _github_request
    issues = _list_open_issues(requester)
    if issues is None:
        result["status"] = "blocked"
        result["blocked"].append({"reason": "github_open_issue_list_unavailable"})
        report_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return result

    result["scanned"] = len(issues)
    remaining: list[dict] = []

    for issue in sorted(issues, key=_issue_number):
        number = _issue_number(issue)
        if number <= 0:
            continue
        if _protected_issue(issue):
            result["skipped_protected"].append(number)
            continue

        close_labels = sorted(_issue_labels(issue) & EXPLICIT_CLOSE_LABELS)
        if close_labels:
            closed = _close_issue(
                requester,
                issue,
                reason=f"explicit_close_label:{close_labels[0]}",
            )
            if closed is None:
                result["blocked"].append(
                    {"github_issue_number": number, "reason": "explicit_label_close_failed"}
                )
            else:
                result["closed"].append(closed)
            continue

        remaining.append(issue)

    groups: dict[tuple[str, str], list[dict]] = {}
    for issue in remaining:
        key = _managed_key(issue)
        if key is not None:
            groups.setdefault(key, []).append(issue)

    for key, rows in sorted(groups.items()):
        if len(rows) < 2:
            continue
        newest = max(rows, key=_issue_number)
        newest_number = _issue_number(newest)
        result["kept_current"].append(
            {
                "github_issue_number": newest_number,
                "managed_kind": key[0],
                "fingerprint": key[1],
            }
        )
        for issue in sorted(rows, key=_issue_number):
            number = _issue_number(issue)
            if number == newest_number:
                continue
            closed = _close_issue(
                requester,
                issue,
                reason=(
                    f"superseded_managed_record:{key[0]}:{key[1]}:"
                    f"newer_issue=#{newest_number}"
                ),
            )
            if closed is None:
                result["blocked"].append(
                    {"github_issue_number": number, "reason": "managed_supersession_close_failed"}
                )
            else:
                result["closed"].append(closed)

    closed_numbers = {int(row["github_issue_number"]) for row in result["closed"]}
    for issue in sorted(remaining, key=_issue_number):
        number = _issue_number(issue)
        if number <= 0 or number in closed_numbers:
            continue
        route = _routing_target(issue, root)
        if route is None:
            continue
        target, reason = route
        new_body = _append_routing_target(str(issue.get("body") or ""), target, reason)
        updated = requester("PATCH", f"/issues/{number}", {"body": new_body})
        if not isinstance(updated, dict) or str(updated.get("body") or "") != new_body:
            result["blocked"].append(
                {"github_issue_number": number, "reason": "deterministic_target_route_failed"}
            )
            continue
        result["routed"].append(
            {"github_issue_number": number, "target": target, "reason": reason}
        )

    if result["blocked"]:
        result["status"] = "partial" if result["closed"] or result["routed"] else "blocked"
    report_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    result = cleanup_obsolete_github_issues(root)
    print(json.dumps(result, sort_keys=True))
    return 0 if result["status"] in {"ok", "not_repository_runtime"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
