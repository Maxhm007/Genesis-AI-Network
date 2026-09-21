from __future__ import annotations

import argparse
import json
import os
import subprocess
from datetime import datetime, timezone

MARKER = "<!-- genesis-discovery-silence-watchdog -->"
TITLE = "[Genesis Discovery] Issue-opening lanes are silent"
LABEL = "genesis-discovery-watchdog"


def _run(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, text=True, capture_output=True, check=False)


def _parse_time(value: str) -> datetime | None:
    value = str(value or "").strip()
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _list_issues(repository: str) -> list[dict]:
    result = _run([
        "gh", "issue", "list", "--repo", repository,
        "--state", "all", "--limit", "100",
        "--json", "number,title,body,state,url,createdAt,closedAt,labels",
    ])
    if result.returncode != 0:
        raise RuntimeError(f"issue lookup failed: {result.stderr[-1200:]}")
    rows = json.loads(result.stdout or "[]")
    return rows if isinstance(rows, list) else []


def _ensure_label(repository: str) -> None:
    _run([
        "gh", "label", "create", LABEL,
        "--repo", repository,
        "--color", "b60205",
        "--description", "Genesis discovery lanes have stopped producing new issues",
        "--force",
    ])


def _latest_issue_time(issues: list[dict]) -> datetime | None:
    values = [_parse_time(row.get("createdAt")) for row in issues if isinstance(row, dict)]
    values = [value for value in values if value is not None]
    return max(values) if values else None


def _existing_open_watchdog(issues: list[dict]) -> dict | None:
    for row in issues:
        if str(row.get("state") or "").upper() != "OPEN":
            continue
        if MARKER in str(row.get("body") or "") or str(row.get("title") or "") == TITLE:
            return row
    return None


def check(repository: str, *, silence_hours: float, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    issues = _list_issues(repository)
    existing = _existing_open_watchdog(issues)
    if existing is not None:
        return {
            "status": "watchdog_issue_already_open",
            "issue_number": existing.get("number"),
            "issue_url": existing.get("url"),
        }

    latest = _latest_issue_time(issues)
    if latest is None:
        age_hours = float("inf")
    else:
        age_hours = max(0.0, (now - latest).total_seconds() / 3600.0)

    if age_hours < silence_hours:
        return {
            "status": "healthy",
            "latest_issue_created_at": latest.isoformat() if latest else None,
            "silence_hours": round(age_hours, 3),
            "threshold_hours": silence_hours,
        }

    _ensure_label(repository)
    body = f"""{MARKER}
Genesis detected a repository-wide issue-opening silence condition.

- Latest GitHub issue creation: {latest.isoformat() if latest else 'none found'}
- Silence duration: {age_hours:.2f} hours
- Threshold: {silence_hours:.2f} hours
- Detection lane: deterministic, model-independent discovery watchdog

### Objective
Diagnose why Genesis discovery lanes are not producing fresh grounded issues even though scheduled discovery workflows continue to run.

### Acceptance
- Inspect the main GitHub Issue Discovery, DeepSeek self-development discovery, Recent AI Capability Discovery, and Action Failure Watcher.
- Identify whether the blocker is model startup/inference, backlog governor deferral, duplicate suppression, candidate exhaustion, workflow failure, or stale discovery state.
- Restore at least one healthy bounded issue-opening path.
- Keep this same issue authoritative until verified.
- Do not weaken security, issue-governance, protected-file, validation, or owner-control boundaries.
"""
    created = _run([
        "gh", "issue", "create",
        "--repo", repository,
        "--title", TITLE,
        "--body", body,
        "--label", f"{LABEL},genesis-autonomous",
    ])
    if created.returncode != 0:
        raise RuntimeError(f"watchdog issue creation failed: {created.stderr[-1200:]}")
    url = created.stdout.strip().splitlines()[-1] if created.stdout.strip() else ""
    return {
        "status": "watchdog_issue_opened",
        "issue_url": url,
        "silence_hours": round(age_hours, 3),
        "threshold_hours": silence_hours,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Detect prolonged Genesis issue-opening silence.")
    parser.add_argument("--repository", default=os.environ.get("GITHUB_REPOSITORY", ""))
    parser.add_argument("--silence-hours", type=float, default=float(os.environ.get("GENESIS_DISCOVERY_SILENCE_HOURS", "6")))
    args = parser.parse_args()
    repository = str(args.repository or "").strip()
    if not repository:
        raise SystemExit("repository is required")
    result = check(repository, silence_hours=max(1.0, args.silence_hours))
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
