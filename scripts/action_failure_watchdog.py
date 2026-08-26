from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import subprocess
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_PATH = ROOT / "runtime" / "action_failure_watchdog.json"
MARKER_NAME = "genesis-action-failure"
FAILURE_CONCLUSIONS = {"failure", "timed_out", "startup_failure", "action_required"}
MAX_LOG_CHARS = 2400
MAX_REPAIR_CYCLES = 3
ACTION_QUEUE_LABELS = (
    "genesis-action-verifying",
    "genesis-action-autonomous",
    "genesis-action-retry",
    "genesis-action-blocked",
)

Runner = Callable[..., subprocess.CompletedProcess[str]]


def _default_runner(args: list[str], **kwargs) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, **kwargs)


def _compact_metadata(metadata: dict) -> dict:
    keys = (
        "fingerprint",
        "workflow_id",
        "workflow_name",
        "workflow_path",
        "run_id",
        "run_attempt",
        "head_sha",
        "event",
        "failed_job",
        "failed_step",
        "phase",
        "promoted_sha",
        "repair_cycles",
    )
    compact = {key: metadata.get(key) for key in keys if metadata.get(key) not in (None, "")}
    compact["repair_cycles"] = int(compact.get("repair_cycles") or 0)
    return compact


def encode_metadata(metadata: dict) -> str:
    payload = json.dumps(_compact_metadata(metadata), sort_keys=True, separators=(",", ":")).encode("utf-8")
    token = base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")
    return f"<!-- {MARKER_NAME}: {token} -->"


def decode_metadata(text: str) -> dict | None:
    match = re.search(rf"<!--\s*{re.escape(MARKER_NAME)}:\s*([A-Za-z0-9_-]+)\s*-->", str(text or ""))
    if not match:
        return None
    token = match.group(1)
    token += "=" * ((4 - len(token) % 4) % 4)
    try:
        value = json.loads(base64.urlsafe_b64decode(token.encode("ascii")).decode("utf-8"))
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def replace_metadata(body: str, metadata: dict) -> str:
    marker = encode_metadata(metadata)
    pattern = rf"<!--\s*{re.escape(MARKER_NAME)}:\s*[A-Za-z0-9_-]+\s*-->"
    if re.search(pattern, body or ""):
        return re.sub(pattern, marker, body, count=1)
    return (body.rstrip() + "\n\n" + marker + "\n") if body else marker + "\n"


def sanitize_log_excerpt(text: str) -> str:
    value = str(text or "")
    value = re.sub(r"(?i)(authorization:\s*(?:bearer|token)\s+)\S+", r"\1[REDACTED]", value)
    value = re.sub(r"\b(?:gh[pousr]_|github_pat_)[A-Za-z0-9_]{12,}\b", "[REDACTED_TOKEN]", value)
    value = re.sub(r"(?i)(secret|token|password|api[_-]?key)\s*[=:]\s*[^\s]+", r"\1=[REDACTED]", value)
    lines = [line[-500:] for line in value.splitlines() if line.strip()]
    return "\n".join(lines)[-MAX_LOG_CHARS:]


def _normalize_failure_identity(value: object) -> str:
    text = str(value or "").strip().casefold()
    # Matrix validators and their A/B security steps are independent evidence
    # for the same underlying workflow defect, not separate repair roots.
    text = re.sub(r"\bsecurity\s+review(?:\s+candidate)?\s+[ab]\b", "security review", text)
    text = re.sub(r"\bvalidator[_\s/-]*[ab]\b", "validator", text)
    text = re.sub(r"\bcandidate[_\s/-]*[ab]\b", "candidate", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def failure_fingerprint(metadata: dict) -> str:
    material = {
        "workflow_id": int(metadata.get("workflow_id") or 0),
        "workflow_path": str(metadata.get("workflow_path") or ""),
        "failed_job": _normalize_failure_identity(metadata.get("failed_job")),
        "failed_step": _normalize_failure_identity(metadata.get("failed_step")),
    }
    payload = json.dumps(material, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def failure_root_fingerprint(metadata: dict) -> str:
    return failure_fingerprint(metadata)


def actionable_run(run: dict, *, current_run_id: int | None = None) -> bool:
    try:
        run_id = int(run.get("id") or 0)
    except (TypeError, ValueError):
        return False
    if current_run_id and run_id == current_run_id:
        return False
    if str(run.get("status") or "") != "completed":
        return False
    if str(run.get("conclusion") or "") not in FAILURE_CONCLUSIONS:
        return False
    if str(run.get("event") or "") in {"pull_request", "pull_request_target"}:
        return False
    return str(run.get("head_branch") or "") == "main"


def select_actionable_run(runs: list[dict], *, current_run_id: int | None = None) -> dict | None:
    eligible = [run for run in runs if actionable_run(run, current_run_id=current_run_id)]
    eligible.sort(key=lambda row: (str(row.get("updated_at") or row.get("created_at") or ""), int(row.get("id") or 0)), reverse=True)
    return eligible[0] if eligible else None


def _run_json(runner: Runner, args: list[str]) -> object:
    result = runner(args, text=True, capture_output=True, check=False)
    if result.returncode != 0:
        raise RuntimeError((result.stderr or result.stdout or "command failed")[-1500:])
    return json.loads(result.stdout or "{}")


def _issue_labels(issue: dict) -> set[str]:
    labels = issue.get("labels") or []
    values: set[str] = set()
    for item in labels:
        if isinstance(item, dict):
            values.add(str(item.get("name") or ""))
        else:
            values.add(str(item))
    return {value for value in values if value}


def inspect_failure(repository: str, run: dict, *, runner: Runner = _default_runner) -> dict:
    run_id = int(run["id"])
    jobs_payload = _run_json(runner, ["gh", "api", f"repos/{repository}/actions/runs/{run_id}/jobs?per_page=100"])
    jobs = list(jobs_payload.get("jobs") or []) if isinstance(jobs_payload, dict) else []
    failed_job = "workflow"
    failed_step = "unknown"
    for job in jobs:
        if str(job.get("conclusion") or "") not in FAILURE_CONCLUSIONS:
            continue
        failed_job = str(job.get("name") or "workflow")[:180]
        for step in job.get("steps") or []:
            if str(step.get("conclusion") or "") in FAILURE_CONCLUSIONS:
                failed_step = str(step.get("name") or "unknown")[:220]
                break
        break

    logs = runner(["gh", "run", "view", str(run_id), "--repo", repository, "--log-failed"], text=True, capture_output=True, check=False)
    excerpt = sanitize_log_excerpt((logs.stdout or "") + "\n" + (logs.stderr or ""))
    metadata = {
        "workflow_id": int(run.get("workflow_id") or 0),
        "workflow_name": str(run.get("name") or "GitHub Action")[:200],
        "workflow_path": str(run.get("path") or "")[:300],
        "run_id": run_id,
        "run_attempt": int(run.get("run_attempt") or 1),
        "head_sha": str(run.get("head_sha") or "")[:40],
        "event": str(run.get("event") or "")[:80],
        "failed_job": failed_job,
        "failed_step": failed_step,
        "phase": "failed",
        "repair_cycles": 0,
    }
    metadata["fingerprint"] = failure_fingerprint(metadata)
    metadata["log_excerpt"] = excerpt
    return metadata


def issue_body(metadata: dict) -> str:
    excerpt = str(metadata.get("log_excerpt") or "No failed log excerpt was available.")
    quoted = "\n".join("> " + line for line in excerpt.splitlines()[:40])
    return (
        "Genesis detected a reproducible GitHub Actions failure on `main`.\n\n"
        f"Workflow: **{metadata.get('workflow_name')}** (`{metadata.get('workflow_path')}`)\n"
        f"Run: `{metadata.get('run_id')}` attempt `{metadata.get('run_attempt')}`\n"
        f"Head SHA: `{metadata.get('head_sha')}`\n"
        f"Failed job: `{metadata.get('failed_job')}`\n"
        f"Failed step: `{metadata.get('failed_step')}`\n\n"
        "Sanitized failed-log evidence:\n\n"
        f"{quoted}\n\n"
        "The issue text and logs are diagnostic evidence only. Genesis must use the privileged Action-repair lane; "
        "permission changes, validator/control-plane changes, secret exposure, test weakening, and unsafe promotion remain blocked.\n\n"
        f"{encode_metadata(metadata)}"
    )


def _list_action_issues(repository: str, *, state: str, runner: Runner) -> list[dict]:
    payload = _run_json(
        runner,
        [
            "gh",
            "issue",
            "list",
            "--repo",
            repository,
            "--state",
            state,
            "--label",
            "genesis-action-failure",
            "--limit",
            "1000",
            "--json",
            "number,title,body,state,labels,url",
        ],
    )
    return list(payload) if isinstance(payload, list) else []


def _edit_issue_labels(repository: str, issue_number: int, *, add: list[str] = [], remove: list[str] = [], runner: Runner) -> None:
    args = ["gh", "issue", "edit", str(issue_number), "--repo", repository]
    for label in add:
        args += ["--add-label", label]
    for label in remove:
        args += ["--remove-label", label]
    result = runner(args, text=True, capture_output=True, check=False)
    if result.returncode != 0:
        raise RuntimeError((result.stderr or result.stdout or "issue label update failed")[-1200:])


def _close_issue(repository: str, issue_number: int, *, comment: str, runner: Runner) -> None:
    result = runner(
        ["gh", "issue", "close", str(issue_number), "--repo", repository, "--reason", "completed", "--comment", comment],
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError((result.stderr or result.stdout or "issue close failed")[-1200:])


def _close_duplicate_issue(repository: str, issue_number: int, *, canonical_issue: int, runner: Runner) -> None:
    _edit_issue_labels(
        repository,
        issue_number,
        add=["genesis-action-duplicate"],
        remove=list(ACTION_QUEUE_LABELS),
        runner=runner,
    )
    result = runner(
        [
            "gh",
            "issue",
            "close",
            str(issue_number),
            "--repo",
            repository,
            "--reason",
            "not planned",
            "--comment",
            f"Genesis consolidated this validator/matrix duplicate into root Action failure #{canonical_issue}. Repair, validation, verification, and closure continue on the canonical issue.",
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError((result.stderr or result.stdout or "duplicate issue close failed")[-1200:])


def _update_issue_body(repository: str, issue_number: int, body: str, runner: Runner) -> None:
    result = runner(["gh", "issue", "edit", str(issue_number), "--repo", repository, "--body", body], text=True, capture_output=True, check=False)
    if result.returncode != 0:
        raise RuntimeError((result.stderr or result.stdout or "issue body update failed")[-1200:])


def _lifecycle_label(issues: list[dict]) -> str | None:
    for label in ACTION_QUEUE_LABELS:
        if any(label in _issue_labels(issue) for issue in issues):
            return label
    return None


def deduplicate_open_issues(repository: str, *, runner: Runner = _default_runner) -> list[dict]:
    issues = _list_action_issues(repository, state="open", runner=runner)
    groups: dict[str, list[dict]] = {}
    for issue in issues:
        metadata = decode_metadata(str(issue.get("body") or ""))
        if not metadata:
            continue
        root = failure_root_fingerprint(metadata)
        groups.setdefault(root, []).append(issue)

    actions: list[dict] = []
    for root, group in groups.items():
        if len(group) < 2:
            continue
        group.sort(key=lambda issue: int(issue.get("number") or 0))
        canonical = group[0]
        canonical_number = int(canonical.get("number") or 0)
        lifecycle = _lifecycle_label(group)
        source_candidates = [issue for issue in group if lifecycle and lifecycle in _issue_labels(issue)] or group
        source = max(
            source_candidates,
            key=lambda issue: int((decode_metadata(str(issue.get("body") or "")) or {}).get("run_id") or 0),
        )
        merged = dict(decode_metadata(str(source.get("body") or "")) or {})
        merged["fingerprint"] = root
        merged["repair_cycles"] = max(
            int((decode_metadata(str(issue.get("body") or "")) or {}).get("repair_cycles") or 0)
            for issue in group
        )
        merged_body = replace_metadata(str(source.get("body") or canonical.get("body") or ""), merged)
        _update_issue_body(repository, canonical_number, merged_body, runner)
        if lifecycle:
            _edit_issue_labels(
                repository,
                canonical_number,
                add=[lifecycle],
                remove=[label for label in ACTION_QUEUE_LABELS if label != lifecycle],
                runner=runner,
            )
        duplicates: list[int] = []
        for duplicate in group[1:]:
            number = int(duplicate.get("number") or 0)
            if not number:
                continue
            _close_duplicate_issue(repository, number, canonical_issue=canonical_number, runner=runner)
            duplicates.append(number)
        actions.append({"issue": canonical_number, "action": "root_grouped", "duplicates": duplicates})
    return actions


def _latest_verification_run(repository: str, metadata: dict, *, runner: Runner) -> dict | None:
    workflow_id = int(metadata.get("workflow_id") or 0)
    promoted_sha = str(metadata.get("promoted_sha") or "")
    if not workflow_id or len(promoted_sha) != 40:
        return None
    payload = _run_json(runner, ["gh", "api", f"repos/{repository}/actions/workflows/{workflow_id}/runs?branch=main&per_page=30"])
    runs = list(payload.get("workflow_runs") or []) if isinstance(payload, dict) else []
    matches = [row for row in runs if str(row.get("head_sha") or "") == promoted_sha and int(row.get("id") or 0) != int(metadata.get("run_id") or 0)]
    matches.sort(key=lambda row: int(row.get("id") or 0), reverse=True)
    return matches[0] if matches else None


def reconcile_open_issues(repository: str, *, runner: Runner = _default_runner) -> list[dict]:
    actions: list[dict] = []
    for issue in sorted(_list_action_issues(repository, state="open", runner=runner), key=lambda row: int(row.get("number") or 0)):
        metadata = decode_metadata(str(issue.get("body") or ""))
        if not metadata:
            continue
        number = int(issue["number"])
        labels = _issue_labels(issue)
        phase = str(metadata.get("phase") or "failed")
        if phase == "verifying" or "genesis-action-verifying" in labels:
            verification = _latest_verification_run(repository, metadata, runner=runner)
            if not verification or str(verification.get("status") or "") != "completed":
                continue
            conclusion = str(verification.get("conclusion") or "")
            if conclusion == "success":
                _edit_issue_labels(repository, number, add=["genesis-action-solved"], remove=["genesis-action-verifying", "genesis-action-autonomous", "genesis-action-retry", "genesis-action-blocked"], runner=runner)
                _close_issue(repository, number, comment=f"Genesis verified the repaired Action on fresh main SHA `{metadata.get('promoted_sha')}` and the workflow passed.", runner=runner)
                actions.append({"issue": number, "action": "closed_verified"})
                continue
            if conclusion in FAILURE_CONCLUSIONS:
                metadata.update({
                    "run_id": int(verification.get("id") or 0),
                    "run_attempt": int(verification.get("run_attempt") or 1),
                    "head_sha": str(verification.get("head_sha") or ""),
                    "phase": "failed",
                })
                metadata["fingerprint"] = failure_root_fingerprint(metadata)
                body = replace_metadata(str(issue.get("body") or ""), metadata)
                _update_issue_body(repository, number, body, runner)
                if int(metadata.get("repair_cycles") or 0) >= MAX_REPAIR_CYCLES:
                    _edit_issue_labels(repository, number, add=["genesis-action-blocked"], remove=["genesis-action-verifying", "genesis-action-autonomous", "genesis-action-retry"], runner=runner)
                    actions.append({"issue": number, "action": "blocked_after_verification"})
                else:
                    _edit_issue_labels(repository, number, add=["genesis-action-autonomous"], remove=["genesis-action-verifying", "genesis-action-retry", "genesis-action-blocked"], runner=runner)
                    actions.append({"issue": number, "action": "repair_requeued"})
                continue

        run_id = int(metadata.get("run_id") or 0)
        if not run_id:
            continue
        current = _run_json(runner, ["gh", "api", f"repos/{repository}/actions/runs/{run_id}"])
        if not isinstance(current, dict) or str(current.get("status") or "") != "completed":
            continue
        attempt = int(current.get("run_attempt") or 1)
        conclusion = str(current.get("conclusion") or "")
        if attempt >= 2 and conclusion == "success":
            _edit_issue_labels(repository, number, add=["genesis-action-transient"], remove=["genesis-action-retry", "genesis-action-autonomous"], runner=runner)
            _close_issue(repository, number, comment="Genesis retried the failed Action once and it passed without a code change; classified as transient.", runner=runner)
            actions.append({"issue": number, "action": "closed_transient"})
        elif attempt >= 2 and conclusion in FAILURE_CONCLUSIONS and "genesis-action-autonomous" not in labels:
            metadata["run_attempt"] = attempt
            metadata["fingerprint"] = failure_root_fingerprint(metadata)
            _update_issue_body(repository, number, replace_metadata(str(issue.get("body") or ""), metadata), runner)
            _edit_issue_labels(repository, number, add=["genesis-action-autonomous"], remove=["genesis-action-retry"], runner=runner)
            actions.append({"issue": number, "action": "authorized_repair"})
    return actions


def open_new_failure(repository: str, *, runner: Runner = _default_runner) -> dict:
    open_issues = _list_action_issues(repository, state="open", runner=runner)
    known_roots = {
        failure_root_fingerprint(metadata)
        for issue in open_issues
        if (metadata := decode_metadata(str(issue.get("body") or "")))
    }
    payload = _run_json(runner, ["gh", "api", f"repos/{repository}/actions/runs?branch=main&per_page=100"])
    runs = list(payload.get("workflow_runs") or []) if isinstance(payload, dict) else []
    current_run_id = int(os.environ.get("GITHUB_RUN_ID", "0") or 0) or None
    for run in sorted(runs, key=lambda row: int(row.get("id") or 0)):
        if not actionable_run(run, current_run_id=current_run_id):
            continue
        metadata = inspect_failure(repository, run, runner=runner)
        root = failure_root_fingerprint(metadata)
        if root in known_roots:
            continue
        metadata["fingerprint"] = root
        created = runner(
            [
                "gh",
                "issue",
                "create",
                "--repo",
                repository,
                "--title",
                f"Genesis Action failure: {metadata['workflow_name']} / {metadata['failed_step']}"[:240],
                "--body",
                issue_body(metadata),
                "--label",
                "genesis-action-failure",
                "--label",
                "genesis-action-retry",
            ],
            text=True,
            capture_output=True,
            check=False,
        )
        if created.returncode != 0:
            raise RuntimeError((created.stderr or created.stdout or "issue creation failed")[-1500:])
        return {"status": "issue_opened", "url": created.stdout.strip().splitlines()[-1], "metadata": _compact_metadata(metadata)}
    return {"status": "no_new_failure"}


def retry_once(repository: str, *, runner: Runner = _default_runner) -> dict:
    issues = _run_json(runner, ["gh", "issue", "list", "--repo", repository, "--state", "open", "--label", "genesis-action-retry", "--limit", "100", "--json", "number,body"])
    rows = sorted(list(issues) if isinstance(issues, list) else [], key=lambda row: int(row.get("number") or 0))
    seen_roots: set[str] = set()
    for issue in rows:
        metadata = decode_metadata(str(issue.get("body") or ""))
        if not metadata:
            continue
        root = failure_root_fingerprint(metadata)
        if root in seen_roots:
            continue
        seen_roots.add(root)
        run_id = int(metadata.get("run_id") or 0)
        if not run_id:
            continue
        run = _run_json(runner, ["gh", "api", f"repos/{repository}/actions/runs/{run_id}"])
        if not isinstance(run, dict):
            continue
        if str(run.get("status") or "") == "completed" and str(run.get("conclusion") or "") in FAILURE_CONCLUSIONS and int(run.get("run_attempt") or 1) < 2:
            result = runner(["gh", "run", "rerun", str(run_id), "--failed", "--repo", repository], text=True, capture_output=True, check=False)
            if result.returncode != 0:
                return {"status": "retry_unavailable", "run_id": run_id, "error": (result.stderr or result.stdout)[-1000:]}
            return {"status": "retry_requested", "run_id": run_id, "issue_number": int(issue["number"])}
    return {"status": "no_retry_needed"}


def apply_recovery_status(repository: str, status_path: Path, *, runner: Runner = _default_runner) -> dict:
    payload = json.loads(Path(status_path).read_text(encoding="utf-8"))
    issue_number = int(payload.get("issue_number") or 0)
    if not issue_number:
        return {"status": "no_issue"}
    issue = _run_json(runner, ["gh", "issue", "view", str(issue_number), "--repo", repository, "--json", "body,labels,state"])
    if not isinstance(issue, dict):
        raise RuntimeError("issue lookup did not return an object")
    metadata = decode_metadata(str(issue.get("body") or "")) or {}
    cycles = max(int(metadata.get("repair_cycles") or 0), int(payload.get("repair_cycles") or 0))
    if str(payload.get("status") or "") == "promoted":
        cycles += 1
        metadata.update({
            "phase": "verifying",
            "promoted_sha": str(payload.get("promoted_sha") or ""),
            "repair_cycles": cycles,
            "workflow_id": int(payload.get("workflow_id") or metadata.get("workflow_id") or 0),
            "workflow_path": str(payload.get("workflow_path") or metadata.get("workflow_path") or ""),
        })
        metadata["fingerprint"] = failure_root_fingerprint(metadata)
        _update_issue_body(repository, issue_number, replace_metadata(str(issue.get("body") or ""), metadata), runner)
        _edit_issue_labels(repository, issue_number, add=["genesis-action-verifying"], remove=["genesis-action-autonomous", "genesis-action-retry", "genesis-action-blocked"], runner=runner)
        runner(["gh", "issue", "comment", str(issue_number), "--repo", repository, "--body", f"Genesis promoted validated Action-repair SHA `{metadata['promoted_sha']}`. The issue remains open until a fresh run of the repaired workflow passes."], text=True, capture_output=True, check=False)
        return {"status": "verifying", "issue_number": issue_number, "repair_cycles": cycles}

    cycles += 1
    metadata["repair_cycles"] = cycles
    metadata["phase"] = "failed"
    metadata["fingerprint"] = failure_root_fingerprint(metadata)
    _update_issue_body(repository, issue_number, replace_metadata(str(issue.get("body") or ""), metadata), runner)
    if cycles >= MAX_REPAIR_CYCLES:
        _edit_issue_labels(repository, issue_number, add=["genesis-action-blocked"], remove=["genesis-action-autonomous", "genesis-action-retry", "genesis-action-verifying"], runner=runner)
        outcome = "blocked"
    else:
        _edit_issue_labels(repository, issue_number, add=["genesis-action-autonomous"], remove=["genesis-action-retry", "genesis-action-verifying", "genesis-action-blocked"], runner=runner)
        outcome = "requeued"
    excerpt = sanitize_log_excerpt(str(payload.get("failure_excerpt") or "privileged validation did not produce a promotable candidate"))
    runner(["gh", "issue", "comment", str(issue_number), "--repo", repository, "--body", f"Genesis Action repair validation did not promote this attempt.\n\n```text\n{excerpt}\n```\n\nOutcome: `{outcome}`."], text=True, capture_output=True, check=False)
    return {"status": outcome, "issue_number": issue_number, "repair_cycles": cycles}


def run(repository: str, *, runner: Runner = _default_runner) -> dict:
    deduplicated = deduplicate_open_issues(repository, runner=runner)
    reconciled = reconcile_open_issues(repository, runner=runner)
    opened = open_new_failure(repository, runner=runner)
    result = {"status": "complete", "deduplicated": deduplicated, "reconciled": reconciled, "discovery": opened}
    EVIDENCE_PATH.parent.mkdir(parents=True, exist_ok=True)
    EVIDENCE_PATH.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", default=os.environ.get("GITHUB_REPOSITORY", ""))
    parser.add_argument("--retry-once", action="store_true")
    parser.add_argument("--apply-recovery-status", type=Path)
    args = parser.parse_args()
    if not args.repository:
        raise SystemExit("repository is required")
    if args.retry_once:
        result = retry_once(args.repository)
    elif args.apply_recovery_status:
        result = apply_recovery_status(args.repository, args.apply_recovery_status)
    else:
        result = run(args.repository)
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
