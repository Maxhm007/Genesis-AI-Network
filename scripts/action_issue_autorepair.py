from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
from pathlib import Path

from genesis.coding import CodingModule
from genesis.issue_discovery import AUTONOMOUS_REPAIR_EXCLUDED
from genesis.selfdev import SelfDevelopmentExecutor, normalize_selfdev_path
from scripts.action_failure_watchdog import decode_metadata, sanitize_log_excerpt

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_PATH = ROOT / "runtime" / "action_repair_candidate.json"
MAX_VALIDATION_ATTEMPTS = 3
MAX_REPLACEMENT_BYTES = 4000

PROTECTED_ACTION_CONTROL_PATHS = {
    ".github/workflows/candidate-pr-gate.yml",
    ".github/workflows/independent-validator-gate.yml",
    ".github/workflows/secret-guard.yml",
    ".github/workflows/action-failure-watchdog.yml",
    ".github/workflows/action-failure-watchdog-backup.yml",
    ".github/workflows/action-failure-retry.yml",
    ".github/workflows/action-repair-candidate.yml",
    ".github/workflows/action-repair-recovery.yml",
    ".github/workflows/action-repair-status.yml",
}


def _git(root: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=root, text=True, capture_output=True, check=check)


def _gh_issue(repository: str, issue_number: int) -> dict:
    result = subprocess.run(
        ["gh", "issue", "view", str(issue_number), "--repo", repository, "--json", "number,title,body,labels,state"],
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError((result.stderr or result.stdout or "issue lookup failed")[-1500:])
    value = json.loads(result.stdout or "{}")
    if not isinstance(value, dict):
        raise RuntimeError("issue lookup did not return an object")
    return value


def extract_related_source_paths(workflow_text: str, root: Path) -> list[str]:
    candidates: list[str] = []
    patterns = (
        r"\bpython(?:3)?\s+([A-Za-z0-9_./-]+\.py)\b",
        r"\bpython(?:3)?\s+-m\s+([A-Za-z0-9_.-]+)\b",
    )
    for pattern in patterns:
        for match in re.finditer(pattern, workflow_text):
            value = match.group(1).replace(".", "/") + ".py" if "-m" in pattern else match.group(1)
            value = value.removeprefix("./")
            if not value.startswith(("genesis/", "scripts/")):
                continue
            if value in AUTONOMOUS_REPAIR_EXCLUDED or value in {"scripts/secret_guard.py", "scripts/privileged_change_gate.py", "scripts/action_repair_guard.py"}:
                continue
            if (root / value).is_file() and value not in candidates:
                candidates.append(value)
    return candidates[:3]


def _numbered(text: str) -> str:
    return "\n".join(f"{index}|{line}" for index, line in enumerate(text.splitlines(), start=1))


def build_objective(metadata: dict, feedback: list[str] | None = None) -> str:
    objective = (
        "Repair the confirmed GitHub Actions failure with exactly one smallest repository edit. "
        f"Workflow {metadata.get('workflow_name')} failed in job {metadata.get('failed_job')} at step {metadata.get('failed_step')}. "
        f"Sanitized failure evidence: {sanitize_log_excerpt(str(metadata.get('log_excerpt') or ''))}. "
        "Preserve workflow purpose, tests, validation, security, permissions, secrets, and promotion safeguards. "
        "Do not change permissions, identity roots, validators, Secret Guard, or the Action self-repair control workflows."
    )
    if feedback:
        objective += " PRIOR_VALIDATION_EVIDENCE: " + " | ".join(feedback[-2:])[-1800:]
    return objective


def propose_edit(root: Path, provider, metadata: dict, allowed_paths: list[str], feedback: list[str] | None = None) -> tuple[str, str]:
    contexts = {path: _numbered((root / path).read_text(encoding="utf-8", errors="replace")[:12000]) for path in allowed_paths[:4]}
    objective = build_objective(metadata, feedback)
    example_path = allowed_paths[0]
    prompt = (
        "ROLE: genesis_privileged_action_repair_engineer\n"
        "Make exactly ONE smallest edit that addresses the confirmed failed Action evidence. Return JSON only as "
        f"{{\"edits\":[{{\"path\":\"{example_path}\",\"start_line\":1,\"end_line\":1,\"new\":\"replacement text\"}}]}}. "
        "Path must exactly match VALID_PATHS. Use only numbered line ranges. Never add/change GitHub permissions, secret access, "
        "pull_request_target, self-hosted runners, validators, security gates, or tests to make a failure disappear.\n"
        f"VALID_PATHS: {json.dumps(allowed_paths)}\n"
        f"OBJECTIVE: {objective}\n"
        f"NUMBERED_CONTEXT: {json.dumps(contexts, sort_keys=True)}\n"
    )
    coding = CodingModule(root)
    last_error: Exception | None = None
    current_prompt = prompt
    for attempt in range(1, 4):
        raw = provider.reason(current_prompt)
        try:
            payload = CodingModule._extract_json(raw)
            edits = payload.get("edits")
            if not isinstance(edits, list) or len(edits) != 1 or not isinstance(edits[0], dict):
                raise ValueError("Action repair requires exactly one edit")
            edit = edits[0]
            path = str(edit.get("path") or "").replace("\\", "/").removeprefix("./")
            if path not in allowed_paths:
                raise ValueError("Action repair edit path is outside VALID_PATHS")
            normalize_selfdev_path(root, path, allow_privileged=True)
            new = edit.get("new")
            if not isinstance(new, str) or len(new.encode("utf-8")) > MAX_REPLACEMENT_BYTES:
                raise ValueError("Action repair replacement is invalid or too large")
            rendered = coding._apply_line_edit(path, edit.get("start_line"), edit.get("end_line"), new)
            return path, rendered
        except Exception as exc:
            last_error = exc
            if attempt >= 3:
                break
            current_prompt = prompt + f"\nRETRY_ERROR: {type(exc).__name__}: {str(exc)[:500]}\nDo not repeat the rejected edit."
    raise ValueError(f"provider failed to produce a bounded Action repair: {last_error}")


def _restore_main(root: Path, failed_branch: str) -> None:
    if not (root / ".git").exists():
        return
    _git(root, "checkout", "main", check=False)
    if failed_branch.startswith("genesis/"):
        _git(root, "branch", "-D", failed_branch, check=False)


def solve_issue(root: Path, repository: str, issue_number: int, *, provider=None, executor=None) -> dict:
    root = Path(root).resolve()
    issue = _gh_issue(repository, issue_number)
    metadata = decode_metadata(str(issue.get("body") or ""))
    if not metadata:
        return {"status": "blocked", "reason": "missing_action_failure_metadata", "issue_number": issue_number}
    if int(metadata.get("repair_cycles") or 0) >= 3:
        return {"status": "blocked", "reason": "repair_cycle_limit_reached", "issue_number": issue_number}

    workflow_path = str(metadata.get("workflow_path") or "").replace("\\", "/")
    if not workflow_path.startswith(".github/workflows/") or not (root / workflow_path).is_file():
        return {"status": "blocked", "reason": "workflow_path_not_current", "issue_number": issue_number}
    if workflow_path in PROTECTED_ACTION_CONTROL_PATHS:
        return {"status": "blocked", "reason": "root_action_control_requires_owner", "issue_number": issue_number, "workflow_path": workflow_path}

    workflow_text = (root / workflow_path).read_text(encoding="utf-8", errors="replace")
    related = extract_related_source_paths(workflow_text, root)
    allowed_paths = [workflow_path, *related]
    provider = provider or CodingModule(root)._provider()
    if provider is None or str(getattr(provider, "name", "")) == "genesis-bootstrap":
        return {"status": "blocked", "reason": "non_bootstrap_provider_required", "issue_number": issue_number}
    executor = executor or SelfDevelopmentExecutor(root)
    feedback: list[str] = []

    for validation_attempt in range(1, MAX_VALIDATION_ATTEMPTS + 1):
        branch = ""
        try:
            edited_path, rendered = propose_edit(root, provider, metadata, allowed_paths, feedback)
            files = {edited_path: rendered}
            if edited_path != workflow_path:
                files[workflow_path] = workflow_text
            proposal = {
                "title": f"Repair Action failure #{issue_number}",
                "provenance": {
                    "initiator": "genesis.action_autorepair",
                    "discovery": "genesis.action_failure_watchdog",
                    "designer": str(getattr(provider, "name", "provider")),
                    "issue_number": issue_number,
                    "failed_run_id": metadata.get("run_id"),
                    "validation_attempt": validation_attempt,
                },
                "files": files,
            }
            result = executor.execute(proposal)
            branch = result.branch
            if result.tests_passed and result.committed and result.commit_sha:
                if not branch.startswith("genesis/privileged-candidate-"):
                    raise RuntimeError("Action repair candidate must use privileged lane")
                pushed = _git(root, "push", "origin", branch, check=False)
                if pushed.returncode != 0:
                    raise RuntimeError((pushed.stderr or pushed.stdout or "candidate push failed")[-1200:])
                _git(root, "checkout", "main", check=False)
                return {
                    "status": "candidate_created",
                    "issue_number": issue_number,
                    "candidate_branch": branch,
                    "candidate_sha": result.commit_sha,
                    "workflow_id": int(metadata.get("workflow_id") or 0),
                    "workflow_path": workflow_path,
                    "failed_run_id": int(metadata.get("run_id") or 0),
                    "repair_cycles": int(metadata.get("repair_cycles") or 0),
                    "provider": str(getattr(provider, "name", "provider")),
                    "changed_files": list(result.changed_files),
                }
            feedback.append(sanitize_log_excerpt(result.message or "candidate tests failed"))
            _restore_main(root, branch)
        except RuntimeError as exc:
            _restore_main(root, branch)
            return {"status": "blocked", "reason": str(exc)[:1800], "issue_number": issue_number, "workflow_path": workflow_path}
        except Exception as exc:
            feedback.append(f"{type(exc).__name__}: {str(exc)[:900]}")
            _restore_main(root, branch)

    return {
        "status": "repair_failed_validation",
        "issue_number": issue_number,
        "workflow_id": int(metadata.get("workflow_id") or 0),
        "workflow_path": workflow_path,
        "failed_run_id": int(metadata.get("run_id") or 0),
        "repair_cycles": int(metadata.get("repair_cycles") or 0),
        "feedback": feedback[-3:],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--issue-number", required=True, type=int)
    parser.add_argument("--repository", default=os.environ.get("GITHUB_REPOSITORY", ""))
    args = parser.parse_args()
    if not args.repository:
        raise SystemExit("repository is required")
    try:
        result = solve_issue(ROOT, args.repository, args.issue_number)
    except Exception as exc:
        result = {"status": "error", "issue_number": args.issue_number, "error": f"{type(exc).__name__}: {exc}"[:1800]}
    EVIDENCE_PATH.parent.mkdir(parents=True, exist_ok=True)
    EVIDENCE_PATH.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    if result.get("status") == "error":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
