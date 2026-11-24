from __future__ import annotations

import argparse
import json
import os
import re
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

from genesis.providers import ProviderRegistry
from genesis.lab_recovery_wake import wake_lab_recovery

ROOT = Path(__file__).resolve().parents[1]
CONFIG = json.loads((ROOT / "config" / "genesis_teammates.json").read_text(encoding="utf-8"))
REPOSITORY = os.environ.get("GITHUB_REPOSITORY", "").strip()
TOKEN = os.environ.get("GITHUB_TOKEN", "").strip() or os.environ.get("GH_TOKEN", "").strip()
API = "https://api.github.com"

TEAM_TASK_SOURCE_RE = re.compile(r"Autonomous Genesis development task from issue #(\d+):", re.IGNORECASE)

CURRENT_PROBLEM_MARKER = "<!-- genesis-team-current-problem -->"
PROBLEM_HINTS = (
    "repair status:", "provider_timeout", "provider_error", "malformed json",
    "failed", "failure", "error", "stuck", "blocked", "exhausted",
    "retry_pending", "not produce a verified promotion",
)

ROLE_MAP = {
    "atlas": ("planner", "Architecture and decomposition. Produce a bounded design, dependencies, risks, and handoff in neutral operational language."),
    "forge": ("engineer", "Implementation and repair. Produce the smallest safe implementation path and execution acceptance criteria in neutral operational language."),
    "sentinel": ("validator", "Independent QA and validation. Define pass/fail evidence and reject unsupported completion claims in neutral operational language."),
    "scout": ("researcher", "Research and investigation. Gather repository evidence, unknowns, and the next evidence-producing action in neutral operational language."),
    "recovery": ("reviewer", "Recovery and troubleshooting. Identify why prior attempts failed and require a materially different next strategy in neutral operational language."),
}


def request(method: str, path: str, data: dict | None = None) -> Any:
    if not REPOSITORY or not TOKEN:
        raise RuntimeError("GitHub repository or token not configured in environment.")
    url = f"{API}/repos/{REPOSITORY}{path}" if path.startswith("/") else f"{API}/{path}"
    headers = {
        "Authorization": f"token {TOKEN}",
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "Genesis-Teammate",
    }
    body = json.dumps(data).encode("utf-8") if data is not None else None
    req = urllib.request.Request(url, data=body, headers=headers, method=method.upper())
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw) if raw else None
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"GitHub API {method} {url} failed with status {e.code}: {error_body}") from e


def paged_get(path: str) -> list[dict]:
    rows: list[dict] = []
    page = 1
    while page <= 3:
        suffix = "&" if "?" in path else "?"
        batch = request("GET", f"{path}{suffix}per_page=100&page={page}")
        if not isinstance(batch, list):
            break
        rows.extend(batch)
        if len(batch) < 100:
            break
        page += 1
    return rows


def issue_comments(issue_number: int) -> list[dict]:
    return paged_get(f"/issues/{issue_number}/comments")


def latest_problem_comment(comments: list[dict], fallback: str = "") -> str:
    """Return the newest comment that describes the present unresolved problem."""
    for row in reversed(comments):
        body = str(row.get("body") or "").strip()
        lower = body.lower()
        if not body or body.startswith(CURRENT_PROBLEM_MARKER):
            continue
        if "<!-- genesis-closure-certificate -->" in lower:
            continue
        if "genesis verification evidence:" in lower or "verified and promoted" in lower:
            continue
        if any(token in lower for token in PROBLEM_HINTS):
            return body[:3500]
    return str(fallback or "").strip()[:3500]


def current_problem_context(issue: dict) -> str:
    number = int(issue.get("number") or 0)
    title = str(issue.get("title") or "")
    body = str(issue.get("body") or "")
    latest = latest_problem_comment(issue_comments(number), fallback=body)
    return (
        f"Current authoritative problem for issue #{number} ({title}):\n"
        f"{latest}\n\n"
        "Rule: solve the newest current problem first. If an attempt fails or the problem changes, "
        "append a new issue comment describing the exact present failure before retrying."
    )


def reconcile_legacy_team_tasks() -> list[int]:
    """Retire old Nexus execution issues that duplicate an authoritative source issue."""
    protected = set(int(v) for v in CONFIG.get("workspaces", {}).values())
    retired: list[int] = []
    for issue in paged_get("/issues?state=open"):
        number = int(issue.get("number") or 0)
        if number <= 0 or number in protected or issue.get("pull_request"):
            continue
        body = str(issue.get("body") or "")
        if "<!-- genesis-team-task -->" not in body:
            continue
        match = TEAM_TASK_SOURCE_RE.search(body)
        if not match:
            continue
        source_number = int(match.group(1))
        if source_number == number:
            continue
        try:
            source = request("GET", f"/issues/{source_number}")
        except RuntimeError:
            continue
        if not isinstance(source, dict) or source.get("pull_request"):
            continue
        labels = {
            str(row.get("name") or "") if isinstance(row, dict) else str(row or "")
            for row in (issue.get("labels") or [])
        }
        if "genesis-superseded" not in labels:
            try:
                request("POST", f"/issues/{number}/comments", {
                    "body": f"Superseded by authoritative issue #{source_number}. Retiring legacy duplicate task."
                })
                request("PATCH", f"/issues/{number}", {"state": "closed", "state_reason": "completed"})
            except RuntimeError:
                pass
        retired.append(number)
    return retired


def main() -> int:
    parser = argparse.ArgumentParser(description="Genesis Teammate runner")
    parser.add_argument("role", choices=list(ROLE_MAP.keys()))
    parser.add_argument("--issue", type=int, help="Optional issue number to target directly")
    args = parser.parse_args()

    reconcile_legacy_team_tasks()

    workspace_map = CONFIG.get("workspaces", {})
    role_name = args.role
    issue_num = args.issue or workspace_map.get(role_name)
    if not issue_num:
        print(f"No workspace issue configured for role: {role_name}")
        return 0

    try:
        issue = request("GET", f"/issues/{issue_num}")
    except RuntimeError as e:
        print(f"Failed to fetch issue #{issue_num}: {e}")
        return 1

    problem_text = current_problem_context(issue)
    print(f"Running role '{role_name}' against issue #{issue_num}")
    print(problem_text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())