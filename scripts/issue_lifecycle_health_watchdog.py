from __future__ import annotations

import argparse
import json
import os
import subprocess
from datetime import datetime, timezone

from genesis.issue_opening_manager import annotate_body, submit_agentic_candidate

TITLE = "[Genesis Lifecycle] Automatic issue opening/closing health degraded"
MARKER = "<!-- genesis-issue-lifecycle-health-watchdog -->"
LABEL = "genesis-lifecycle-health"
OPENING_WORKFLOW = "Genesis Issue Opening Manager"
CLOSURE_WORKFLOW = "Genesis Issue Closure Manager"


def _run(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, text=True, capture_output=True, check=False)


def _parse_time(value: str) -> datetime | None:
    value = str(value or "").strip()
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _api(repository: str, path: str) -> dict | list:
    result = _run(["gh", "api", f"repos/{repository}/{path}"])
    if result.returncode != 0:
        raise RuntimeError(f"GitHub API lookup failed for {path}: {result.stderr[-1200:]}")
    data = json.loads(result.stdout or "{}")
    return data


def _latest_workflow_run(repository: str, workflow_name: str) -> dict | None:
    data = _api(repository, "actions/runs?per_page=100")
    rows = data.get("workflow_runs", []) if isinstance(data, dict) else []
    for row in rows:
        if str(row.get("name") or "") == workflow_name:
            return row
    return None


def _issues(repository: str) -> list[dict]:
    data = _api(repository, "issues?state=all&per_page=100&sort=updated&direction=desc")
    return [
        row for row in (data if isinstance(data, list) else [])
        if isinstance(row, dict) and not row.get("pull_request")
    ]


def _labels(issue: dict) -> set[str]:
    result: set[str] = set()
    for row in issue.get("labels") or []:
        if isinstance(row, dict):
            name = str(row.get("name") or "").strip()
        else:
            name = str(row or "").strip()
        if name:
            result.add(name)
    return result


def evaluate(
    *,
    opening_run: dict | None,
    closure_run: dict | None,
    issues: list[dict],
    now: datetime,
    opening_max_age_minutes: int,
    closure_max_age_minutes: int,
    verified_open_grace_minutes: int,
) -> dict:
    faults: list[str] = []
    evidence: dict[str, object] = {}

    for label, run, max_age in (
        ("opening", opening_run, opening_max_age_minutes),
        ("closing", closure_run, closure_max_age_minutes),
    ):
        if not run:
            faults.append(f"{label}_manager_has_no_recent_run")
            evidence[f"{label}_run"] = None
            continue
        updated = _parse_time(str(run.get("updated_at") or run.get("created_at") or ""))
        age = float("inf") if updated is None else max(0.0, (now - updated).total_seconds() / 60.0)
        status = str(run.get("status") or "")
        conclusion = str(run.get("conclusion") or "")
        evidence[f"{label}_run"] = {
            "id": run.get("id"),
            "status": status,
            "conclusion": conclusion,
            "updated_at": updated.isoformat() if updated else None,
            "age_minutes": round(age, 1),
        }
        if age > max_age:
            faults.append(f"{label}_manager_stale:{age:.1f}m>{max_age}m")
        elif status == "completed" and conclusion not in {"success", "neutral", "skipped"}:
            faults.append(f"{label}_manager_latest_run_{conclusion or 'unknown'}")

    stale_verified: list[int] = []
    for issue in issues:
        if str(issue.get("state") or "").lower() != "open":
            continue
        if "genesis-verified" not in _labels(issue):
            continue
        updated = _parse_time(str(issue.get("updated_at") or ""))
        age = float("inf") if updated is None else max(0.0, (now - updated).total_seconds() / 60.0)
        if age >= verified_open_grace_minutes:
            number = int(issue.get("number") or 0)
            if number > 0:
                stale_verified.append(number)
    if stale_verified:
        faults.append("verified_issues_not_auto_closed:" + ",".join(map(str, stale_verified[:10])))
    evidence["verified_open_issues_past_grace"] = stale_verified[:20]

    return {
        "healthy": not faults,
        "faults": faults,
        "evidence": evidence,
    }


def _existing_open_watchdog(issues: list[dict]) -> dict | None:
    for issue in issues:
        if str(issue.get("state") or "").lower() != "open":
            continue
        if MARKER in str(issue.get("body") or "") or str(issue.get("title") or "") == TITLE:
            return issue
    return None


def check(
    repository: str,
    *,
    now: datetime | None = None,
    opening_max_age_minutes: int = 75,
    closure_max_age_minutes: int = 30,
    verified_open_grace_minutes: int = 20,
) -> dict:
    now = now or datetime.now(timezone.utc)
    issues = _issues(repository)
    assessment = evaluate(
        opening_run=_latest_workflow_run(repository, OPENING_WORKFLOW),
        closure_run=_latest_workflow_run(repository, CLOSURE_WORKFLOW),
        issues=issues,
        now=now,
        opening_max_age_minutes=opening_max_age_minutes,
        closure_max_age_minutes=closure_max_age_minutes,
        verified_open_grace_minutes=verified_open_grace_minutes,
    )
    if assessment["healthy"]:
        return {"status": "healthy", **assessment}

    existing = _existing_open_watchdog(issues)
    if existing is not None:
        return {
            "status": "health_issue_already_open",
            "issue_number": existing.get("number"),
            "issue_url": existing.get("html_url"),
            **assessment,
        }

    token = os.environ.get("GITHUB_TOKEN", "").strip() or os.environ.get("GH_TOKEN", "").strip()
    body = f"""{MARKER}
Genesis detected that the automatic GitHub Issue lifecycle is unhealthy.

### Detected faults
{chr(10).join(f"- {fault}" for fault in assessment["faults"])}

### Evidence
```json
{json.dumps(assessment["evidence"], indent=2, sort_keys=True)}
```

### Objective
Restore autonomous issue opening and issue closing so Genesis can continuously verify that both sides of the lifecycle are functioning without human checks.

### Acceptance
- Diagnose the failing/stale Issue Opening Manager and/or Issue Closure Manager path.
- Confirm scheduled manager execution is current and successful.
- Confirm verified open issues are automatically reconciled and closed within the configured grace period.
- Preserve the single Agentic Issue Opening Authority and Closure Manager; do not create a competing controller.
- Route any required repair through Agentic Lab and keep verification-before-close mandatory.
- Add or update regression coverage for the identified lifecycle failure.
"""
    body = annotate_body(body, "issue-lifecycle-health-watchdog")
    decision = submit_agentic_candidate(
        repository,
        token,
        lane="issue-lifecycle-health-watchdog",
        title=TITLE,
        body=body,
        severity="critical",
        value_score=100.0,
        bypass_backlog=True,
        labels=[LABEL, "genesis-autonomous", "agentic-lab"],
    )
    return {
        "status": "agentic_opening_pending",
        "manager_status": decision.action,
        **assessment,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify Genesis automatic issue opening and closing health.")
    parser.add_argument("--repository", default=os.environ.get("GITHUB_REPOSITORY", ""))
    parser.add_argument("--opening-max-age-minutes", type=int, default=75)
    parser.add_argument("--closure-max-age-minutes", type=int, default=30)
    parser.add_argument("--verified-open-grace-minutes", type=int, default=20)
    args = parser.parse_args()
    repository = str(args.repository or "").strip()
    if not repository:
        raise SystemExit("repository is required")
    result = check(
        repository,
        opening_max_age_minutes=max(15, args.opening_max_age_minutes),
        closure_max_age_minutes=max(10, args.closure_max_age_minutes),
        verified_open_grace_minutes=max(10, args.verified_open_grace_minutes),
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
