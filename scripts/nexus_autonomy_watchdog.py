from __future__ import annotations

import argparse
import json
import os
import subprocess
from datetime import datetime, timezone

from genesis.issue_opening_manager import annotate_body, submit_agentic_candidate

TITLE = "[Nexus Autonomy] Genesis autonomous loop degraded"
MARKER = "<!-- nexus-autonomy-watchdog -->"
NEXUS_ISSUE = 1000
TEAM_WORKFLOW = "Genesis Teammate - Autonomous Development"
AGENTIC_WORKFLOW = "Genesis Agentic Lab Recovery"
ACTIVE_LABELS = {
    "genesis-repair-in-progress",
    "genesis-validating",
    "genesis-claimed",
    "genesis-working",
    "genesis-verifying",
}
IGNORE_LABELS = {
    "genesis-persistent",
    "duplicate",
    "invalid",
    "wontfix",
    "genesis-superseded",
    "performance-indicator",
}


def _run(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, text=True, capture_output=True, check=False)


def _api(repository: str, path: str) -> dict | list:
    result = _run(["gh", "api", f"repos/{repository}/{path}"])
    if result.returncode != 0:
        raise RuntimeError(f"GitHub API lookup failed for {path}: {result.stderr[-1200:]}")
    return json.loads(result.stdout or "{}")


def _parse_time(value: object) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _latest_run(repository: str, workflow_name: str) -> dict | None:
    data = _api(repository, "actions/runs?per_page=100")
    rows = data.get("workflow_runs", []) if isinstance(data, dict) else []
    for row in rows:
        if str(row.get("name") or "") == workflow_name:
            return row
    return None


def _issues(repository: str) -> list[dict]:
    data = _api(repository, "issues?state=open&per_page=100&sort=updated&direction=desc")
    return [
        row for row in (data if isinstance(data, list) else [])
        if isinstance(row, dict) and not row.get("pull_request")
    ]


def _labels(issue: dict) -> set[str]:
    out: set[str] = set()
    for row in issue.get("labels") or []:
        name = str(row.get("name") if isinstance(row, dict) else row or "").strip()
        if name:
            out.add(name)
    return out


def evaluate(
    *,
    team_run: dict | None,
    agentic_run: dict | None,
    issues: list[dict],
    now: datetime,
    team_max_age_minutes: int = 35,
    agentic_max_age_minutes: int = 20,
    stalled_issue_minutes: int = 90,
) -> dict:
    faults: list[str] = []
    evidence: dict[str, object] = {}

    for key, run, max_age in (
        ("team", team_run, team_max_age_minutes),
        ("agentic_lab", agentic_run, agentic_max_age_minutes),
    ):
        if not run:
            faults.append(f"{key}_heartbeat_missing")
            evidence[f"{key}_run"] = None
            continue
        updated = _parse_time(run.get("updated_at") or run.get("created_at"))
        age = float("inf") if updated is None else max(0.0, (now - updated).total_seconds() / 60.0)
        status = str(run.get("status") or "")
        conclusion = str(run.get("conclusion") or "")
        evidence[f"{key}_run"] = {
            "id": run.get("id"),
            "status": status,
            "conclusion": conclusion,
            "updated_at": updated.isoformat() if updated else None,
            "age_minutes": round(age, 1),
        }
        if age > max_age:
            faults.append(f"{key}_heartbeat_stale:{age:.1f}m>{max_age}m")
        elif status == "completed" and conclusion not in {"success", "neutral", "skipped"}:
            faults.append(f"{key}_latest_run_{conclusion or 'unknown'}")

    actionable: list[int] = []
    active: list[int] = []
    stalled: list[int] = []
    for issue in issues:
        labels = _labels(issue)
        if "genesis-autonomous" not in labels or "genesis-verified" in labels or labels & IGNORE_LABELS:
            continue
        number = int(issue.get("number") or 0)
        if number <= 0:
            continue
        actionable.append(number)
        if labels & ACTIVE_LABELS:
            active.append(number)
        updated = _parse_time(issue.get("updated_at"))
        age = float("inf") if updated is None else max(0.0, (now - updated).total_seconds() / 60.0)
        if age >= stalled_issue_minutes and not (labels & ACTIVE_LABELS):
            stalled.append(number)

    if actionable and not active:
        faults.append("actionable_backlog_has_no_active_autonomous_worker")
    if stalled:
        faults.append("stalled_autonomous_issues:" + ",".join(map(str, stalled[:10])))

    evidence["actionable_issue_count"] = len(actionable)
    evidence["active_issue_count"] = len(active)
    evidence["actionable_issues"] = actionable[:20]
    evidence["active_issues"] = active[:20]
    evidence["stalled_issues"] = stalled[:20]

    return {"healthy": not faults, "faults": faults, "evidence": evidence}


def _dispatch(repository: str, workflow: str) -> bool:
    result = _run(["gh", "workflow", "run", workflow, "--repo", repository, "--ref", "main"])
    return result.returncode == 0


def _existing_watchdog(issues: list[dict]) -> dict | None:
    for issue in issues:
        if MARKER in str(issue.get("body") or "") or str(issue.get("title") or "") == TITLE:
            return issue
    return None


def _comment_nexus(repository: str, body: str) -> None:
    _run(["gh", "issue", "comment", str(NEXUS_ISSUE), "--repo", repository, "--body", body])


def _mark_recovered(repository: str, issue: dict, assessment: dict) -> bool:
    number = int(issue.get("number") or 0)
    if number <= 0:
        return False
    evidence = json.dumps(assessment.get("evidence") or {}, sort_keys=True)
    _run([
        "gh", "issue", "comment", str(number), "--repo", repository,
        "--body",
        "<!-- nexus-autonomy-recovered -->\n"
        "Nexus verified that the Genesis autonomous loop is healthy again. "
        f"Evidence: `{evidence}`",
    ])
    result = _run([
        "gh", "issue", "edit", str(number), "--repo", repository,
        "--add-label", "genesis-verified",
    ])
    return result.returncode == 0


def check(
    repository: str,
    *,
    now: datetime | None = None,
    team_max_age_minutes: int = 35,
    agentic_max_age_minutes: int = 20,
    stalled_issue_minutes: int = 90,
) -> dict:
    now = now or datetime.now(timezone.utc)
    issues = _issues(repository)
    assessment = evaluate(
        team_run=_latest_run(repository, TEAM_WORKFLOW),
        agentic_run=_latest_run(repository, AGENTIC_WORKFLOW),
        issues=issues,
        now=now,
        team_max_age_minutes=team_max_age_minutes,
        agentic_max_age_minutes=agentic_max_age_minutes,
        stalled_issue_minutes=stalled_issue_minutes,
    )
    existing = _existing_watchdog(issues)

    if assessment["healthy"]:
        if existing is not None:
            verified = _mark_recovered(repository, existing, assessment)
            _comment_nexus(
                repository,
                "<!-- nexus-autonomy-watchdog-recovered -->\n"
                f"### Nexus autonomy watchdog\nGenesis autonomy recovered. Repair issue #{existing.get('number')} was marked verified.",
            )
            return {
                "status": "healthy_repair_verified" if verified else "healthy_repair_verification_failed",
                "issue_number": existing.get("number"),
                **assessment,
            }
        return {"status": "healthy", **assessment}

    wakes = {
        "team": _dispatch(repository, "genesis-teammate-autonomous-development.yml"),
        "agentic_lab": _dispatch(repository, "genesis-agentic-lab-recovery.yml"),
    }

    if existing is not None:
        _run([
            "gh", "issue", "comment", str(existing.get("number")), "--repo", repository,
            "--body",
            "<!-- nexus-autonomy-watchdog-repeat -->\n"
            "Nexus autonomy watchdog still detects faults:\n"
            + "\n".join(f"- {fault}" for fault in assessment["faults"]),
        ])
        return {
            "status": "repair_issue_already_open",
            "issue_number": existing.get("number"),
            "wakes": wakes,
            **assessment,
        }

    token = os.environ.get("GITHUB_TOKEN", "").strip() or os.environ.get("GH_TOKEN", "").strip()
    body = f"""{MARKER}
Nexus detected that Genesis is not maintaining its autonomous operating loop.

### Detected faults
{chr(10).join(f"- {fault}" for fault in assessment["faults"])}

### Evidence
```json
{json.dumps(assessment["evidence"], indent=2, sort_keys=True)}
```

### Objective
Restore Genesis autonomous operation end-to-end without requiring a human "check now" prompt.

### Acceptance
- Restore the Genesis teammate heartbeat.
- Restore the Agentic Lab recovery heartbeat.
- Ensure actionable autonomous issues have an active worker when backlog exists.
- Recover stalled autonomous issues without creating duplicate repair issues.
- Preserve Nexus as the autonomy supervisor and Agentic Lab as the execution authority.
- Verify recovery with fresh workflow runs and issue-progress evidence before closing this issue.
"""
    body = annotate_body(body, "nexus-autonomy-watchdog")
    decision = submit_agentic_candidate(
        repository,
        token,
        lane="nexus-autonomy-watchdog",
        title=TITLE,
        body=body,
        severity="critical",
        value_score=100.0,
        bypass_backlog=True,
        labels=["nexus-autonomy-watchdog", "genesis-autonomous", "agentic-lab"],
    )
    _dispatch(repository, "genesis-agentic-issue-opening.yml")
    _dispatch(repository, "genesis-agentic-lab-recovery.yml")
    _comment_nexus(
        repository,
        "<!-- nexus-autonomy-watchdog-fault -->\n"
        "### Nexus autonomy watchdog\n"
        "Genesis autonomy degradation detected. A critical repair issue has been submitted to the single issue-opening authority and Agentic Lab has been awakened.\n\n"
        + "\n".join(f"- {fault}" for fault in assessment["faults"]),
    )
    return {
        "status": "repair_issue_submitted",
        "opening_status": decision.action,
        "wakes": wakes,
        **assessment,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Nexus watchdog for Genesis autonomous operation.")
    parser.add_argument("--repository", default=os.environ.get("GITHUB_REPOSITORY", ""))
    parser.add_argument("--team-max-age-minutes", type=int, default=35)
    parser.add_argument("--agentic-max-age-minutes", type=int, default=20)
    parser.add_argument("--stalled-issue-minutes", type=int, default=90)
    args = parser.parse_args()
    repository = str(args.repository or "").strip()
    if not repository:
        raise SystemExit("repository is required")
    result = check(
        repository,
        team_max_age_minutes=max(20, args.team_max_age_minutes),
        agentic_max_age_minutes=max(10, args.agentic_max_age_minutes),
        stalled_issue_minutes=max(45, args.stalled_issue_minutes),
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
