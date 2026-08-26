from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.action_failure_watchdog import decode_metadata

FAILURE_LABEL = "genesis-action-failure"
SOLVED_LABEL = "genesis-action-solved"
REMOVE_LABELS = (
    "genesis-action-autonomous",
    "genesis-action-retry",
    "genesis-action-verifying",
    "genesis-action-blocked",
)


def _run_json(args: list[str]) -> object:
    result = subprocess.run(args, text=True, capture_output=True, check=False)
    if result.returncode != 0:
        raise RuntimeError((result.stderr or result.stdout or "command failed")[-1200:])
    return json.loads(result.stdout or "{}")


def _matching_job_passed(jobs: list[dict], failed_job: str) -> bool:
    target = str(failed_job or "").strip()
    if not target or target == "workflow":
        return False
    for job in jobs:
        if str(job.get("name") or "").strip() == target and str(job.get("conclusion") or "") == "success":
            return True
    return False


def find_fresh_success(repository: str, metadata: dict) -> dict | None:
    workflow_id = int(metadata.get("workflow_id") or 0)
    failed_run_id = int(metadata.get("run_id") or 0)
    failed_sha = str(metadata.get("head_sha") or "")
    failed_job = str(metadata.get("failed_job") or "")
    if not workflow_id or not failed_run_id or not failed_job:
        return None
    payload = _run_json([
        "gh",
        "api",
        f"repos/{repository}/actions/workflows/{workflow_id}/runs?branch=main&per_page=50",
    ])
    runs = list(payload.get("workflow_runs") or []) if isinstance(payload, dict) else []
    candidates = [
        run
        for run in runs
        if int(run.get("id") or 0) > failed_run_id
        and str(run.get("status") or "") == "completed"
        and str(run.get("conclusion") or "") == "success"
        and str(run.get("head_branch") or "") == "main"
        and str(run.get("head_sha") or "") != failed_sha
    ]
    candidates.sort(key=lambda row: int(row.get("id") or 0), reverse=True)
    for run in candidates:
        run_id = int(run.get("id") or 0)
        evidence = {
            "run_id": run_id,
            "head_sha": str(run.get("head_sha") or ""),
            "failed_job": failed_job,
        }
        if failed_job == "workflow":
            return evidence
        jobs_payload = _run_json(["gh", "api", f"repos/{repository}/actions/runs/{run_id}/jobs?per_page=100"])
        jobs = list(jobs_payload.get("jobs") or []) if isinstance(jobs_payload, dict) else []
        if _matching_job_passed(jobs, failed_job):
            return evidence
    return None


def _close_verified(repository: str, issue_number: int, evidence: dict) -> None:
    edit = ["gh", "issue", "edit", str(issue_number), "--repo", repository, "--add-label", SOLVED_LABEL]
    for label in REMOVE_LABELS:
        edit += ["--remove-label", label]
    result = subprocess.run(edit, text=True, capture_output=True, check=False)
    if result.returncode != 0:
        raise RuntimeError((result.stderr or result.stdout or "label update failed")[-1200:])
    failed_job = str(evidence.get("failed_job") or "")
    proof = (
        "the whole workflow completed successfully"
        if failed_job == "workflow"
        else f"the previously failed job `{failed_job}` passed"
    )
    comment = (
        "Genesis found fresh verification on a newer `main` revision: "
        f"workflow run `{evidence['run_id']}` completed successfully and {proof} "
        f"on SHA `{evidence['head_sha']}`."
    )
    result = subprocess.run(
        ["gh", "issue", "close", str(issue_number), "--repo", repository, "--reason", "completed", "--comment", comment],
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError((result.stderr or result.stdout or "issue close failed")[-1200:])


def reconcile(repository: str) -> list[dict]:
    payload = _run_json([
        "gh",
        "issue",
        "list",
        "--repo",
        repository,
        "--state",
        "open",
        "--label",
        FAILURE_LABEL,
        "--limit",
        "100",
        "--json",
        "number,body",
    ])
    issues = list(payload) if isinstance(payload, list) else []
    actions: list[dict] = []
    for issue in sorted(issues, key=lambda row: int(row.get("number") or 0)):
        metadata = decode_metadata(str(issue.get("body") or ""))
        if not metadata:
            continue
        evidence = find_fresh_success(repository, metadata)
        if not evidence:
            continue
        number = int(issue.get("number") or 0)
        if not number:
            continue
        _close_verified(repository, number, evidence)
        actions.append({"issue": number, "action": "closed_fresh_success", **evidence})
    return actions


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", required=True)
    args = parser.parse_args()
    print(json.dumps({"reconciled": reconcile(args.repository)}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
