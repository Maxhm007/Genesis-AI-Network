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
AGENTIC_WORKFLOW = "Genesis Agentic Lab Recovery"
ACTIVE_WORK_LABELS = {"genesis-repair-in-progress", "genesis-validating", "genesis-claimed", "genesis-working", "genesis-verifying"}


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


WORKFLOW_FILES = {
    OPENING_WORKFLOW: "genesis-issue-opening-manager.yml",
    CLOSURE_WORKFLOW: "genesis-issue-closure-manager.yml",
    AGENTIC_WORKFLOW: "genesis-agentic-lab-recovery.yml",
}


def _latest_workflow_run(repository: str, workflow_name: str) -> dict | None:
    workflow_file = WORKFLOW_FILES.get(workflow_name)
    if not workflow_file:
        raise ValueError(f"unknown workflow name: {workflow_name}")
    data = _api(repository, f"actions/workflows/{workflow_file}/runs?per_page=1")
    rows = data.get("workflow_runs", []) if isinstance(data, dict) else []
    return rows[0] if rows else None


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


def _dispatch_workflow(repository: str, workflow_file: str) -> bool:
    result = _run([
        "gh", "workflow", "run", workflow_file,
        "--repo", repository,
        "--ref", "main",
    ])
    return result.returncode == 0


def _heal_actions(assessment: dict, repository: str) -> dict:
    faults = list(assessment.get("faults") or [])
    dispatched: list[str] = []
    failed: list[str] = []

    opening_fault = any(fault.startswith("opening_manager_") for fault in faults)
    closing_fault = any(fault.startswith("closing_manager_") for fault in faults)
    verified_stuck = any(fault.startswith("verified_issues_not_auto_closed:") for fault in faults)

    # The lifecycle watchdog is the independent control-plane supervisor.
    # It must not depend on Agentic Lab to restart the managers that feed and
    # close the queue. After repairing those managers it also wakes the
    # authoritative FIFO controller so work resumes immediately.
    for needed, workflow in (
        (opening_fault, "genesis-issue-opening-manager.yml"),
        (closing_fault or verified_stuck, "genesis-issue-closure-manager.yml"),
        (bool(faults), "genesis-agentic-lab-recovery.yml"),
    ):
        if not needed:
            continue
        if _dispatch_workflow(repository, workflow):
            dispatched.append(workflow)
        else:
            failed.append(workflow)
    return {"dispatched": dispatched, "failed": failed}


def _persistent_fault(assessment: dict, *, opening_max_age_minutes: int, closure_max_age_minutes: int, verified_open_grace_minutes: int) -> bool:
    faults = list(assessment.get("faults") or [])
    evidence = assessment.get("evidence") or {}

    # A stale timestamp alone is not a persistent defect. GitHub scheduled
    # workflows may be delayed, and Closure Manager is now primarily event-driven.
    # The watchdog should self-heal stale managers by dispatching them, then only
    # escalate when there is concrete execution failure or verified work remains
    # stuck after the manager has otherwise been running.
    if any(
        "_latest_run_failure" in fault
        or "_latest_run_cancelled" in fault
        or "_latest_run_timed_out" in fault
        for fault in faults
    ):
        return True

    if evidence.get("verified_open_issues_past_grace"):
        closing_failed = any(
            fault.startswith("closing_manager_latest_run_")
            and not fault.endswith("success")
            for fault in faults
        )
        return closing_failed

    return False


def _existing_open_watchdog(issues: list[dict]) -> dict | None:
    for issue in issues:
        if str(issue.get("state") or "").lower() != "open":
            continue
        if MARKER in str(issue.get("body") or "") or str(issue.get("title") or "") == TITLE:
            return issue
    return None


def _verify_recovered_watchdog(repository: str, issue: dict, assessment: dict) -> bool:
    number = int(issue.get("number") or 0)
    if number <= 0:
        return False

    evidence = json.dumps(assessment.get("evidence") or {}, sort_keys=True)
    comment = (
        "<!-- genesis-lifecycle-health-recovered -->\n"
        "Genesis verification evidence: lifecycle watchdog confirmed automatic issue opening "
        "and closing are current and healthy after self-healing. "
        f"Evidence: `{evidence}`"
    )
    comment_result = _run([
        "gh", "issue", "comment", str(number),
        "--repo", repository,
        "--body", comment,
    ])
    if comment_result.returncode != 0:
        return False

    if "genesis-verified" in _labels(issue):
        return True
    result = _run([
        "gh", "issue", "edit", str(number),
        "--repo", repository,
        "--add-label", "genesis-verified",
    ])
    return result.returncode == 0


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
        # Even when opening/closing are healthy, an actionable backlog must
        # continue moving without a human "check now" or manual dispatch.
        actionable = [
            issue for issue in issues
            if str(issue.get("state") or "").lower() == "open"
            and "genesis-autonomous" in _labels(issue)
            and "genesis-verified" not in _labels(issue)
            and not (_labels(issue) & {"genesis-persistent", "duplicate", "invalid", "wontfix", "genesis-superseded", "performance-indicator"})
        ]
        active_work = [
            issue for issue in issues
            if str(issue.get("state") or "").lower() == "open"
            and bool(_labels(issue) & ACTIVE_WORK_LABELS)
        ]
        if actionable and not active_work:
            _dispatch_workflow(repository, "genesis-agentic-lab-recovery.yml")
        existing = _existing_open_watchdog(issues)
        if existing is not None:
            verified = _verify_recovered_watchdog(repository, existing, assessment)
            return {
                "status": "healthy_watchdog_verified" if verified else "healthy_watchdog_verification_failed",
                "issue_number": existing.get("number"),
                "issue_url": existing.get("html_url"),
                **assessment,
            }
        return {"status": "healthy", **assessment}

    healing = _heal_actions(assessment, repository)
    persistent = _persistent_fault(
        assessment,
        opening_max_age_minutes=opening_max_age_minutes,
        closure_max_age_minutes=closure_max_age_minutes,
        verified_open_grace_minutes=verified_open_grace_minutes,
    )
    if not persistent and not healing["failed"]:
        return {"status": "self_heal_dispatched", "healing": healing, **assessment}

    existing = _existing_open_watchdog(issues)
    if existing is not None:
        return {
            "status": "health_issue_already_open",
            "issue_number": existing.get("number"),
            "issue_url": existing.get("html_url"),
            "healing": healing,
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
        "healing": healing,
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
