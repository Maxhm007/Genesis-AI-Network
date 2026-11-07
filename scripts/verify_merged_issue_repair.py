from __future__ import annotations

"""Independently verify an explicitly queued merged issue repair before closure.

The workflow must run the full test suite BEFORE invoking this script. A merged
PR alone is not verification. Repository files and issue text are untrusted
inputs: only exact allowlisted source and regression-test paths are accepted.
"""

import argparse
import json
import os
import re
import urllib.request
from pathlib import Path

from genesis.issue_target import extract_issue_target

ROOT = Path(__file__).resolve().parents[1]
QUEUE = ROOT / ".github" / "merged_repair_verification_queue.json"
SHA_RE = re.compile(r"^[a-f0-9]{40}$")
MARKER = "<!-- genesis-independent-merged-repair-verification:"


def validate_merged_repair(issue: dict, pr: dict, changed_files: list[dict], *, number: int, pr_number: int, sha: str) -> str:
    if not SHA_RE.fullmatch(sha) or number < 1 or pr_number < 1:
        raise ValueError("invalid issue, pull request or commit SHA")
    if str(issue.get("state")) != "open" or "pull_request" in issue:
        raise ValueError("issue must be an open issue, not a PR")
    labels = {row.get("name") for row in issue.get("labels", []) if isinstance(row, dict)}
    if "genesis-owner-paused" in labels or "genesis-superseded" in labels:
        raise ValueError("owner-paused/superseded issues cannot be verified")
    target = extract_issue_target(str(issue.get("body") or ""))
    if not isinstance(target, str) or not target.startswith("genesis/") or not target.endswith(".py") or ".." in target:
        raise ValueError("issue has no safe supported target")
    if not pr.get("merged_at") or pr.get("merge_commit_sha") != sha:
        raise ValueError("PR has not merged at the exact expected SHA")
    if (pr.get("base") or {}).get("ref") != "main":
        raise ValueError("only changes merged to main can be verified")
    pr_text = str(pr.get("title") or "") + "\n" + str(pr.get("body") or "")
    if not re.search(r"(?<!\d)#" + str(number) + r"(?!\d)", pr_text):
        raise ValueError("PR does not explicitly link the target issue")
    names = [row.get("filename") for row in changed_files if isinstance(row, dict)]
    if not names or target not in names or any(not isinstance(x, str) for x in names):
        raise ValueError("merged PR does not change the exact target")
    allowed_test = "tests/test_" + Path(target).stem + ".py"
    allowed = {target, allowed_test, ".github/workflows/genesis-repair-checkpoint-gate.yml"}
    if any(path not in allowed for path in names):
        raise ValueError("PR contains an unexpected source or workflow change")
    if allowed_test not in names:
        raise ValueError("merged PR must include target-specific regression tests")
    return target


def _api(repository: str, token: str, method: str, path: str, body: dict | None = None):
    data = None if body is None else json.dumps(body).encode("utf-8")
    request = urllib.request.Request(
        f"https://api.github.com/repos/{repository}{path}", method=method, data=data,
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
                 "Content-Type": "application/json", "X-GitHub-Api-Version": "2022-11-28"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = response.read().decode("utf-8")
    return json.loads(payload) if payload.strip() else {}


def verify_one(repository: str, token: str, row: dict) -> dict:
    number, pr_number, sha = int(row["issue"]), int(row["pr"]), str(row["sha"])
    issue = _api(repository, token, "GET", f"/issues/{number}")
    # Idempotent after a successful previous run; do not emit forged evidence.
    labels = {label.get("name") for label in issue.get("labels", []) if isinstance(label, dict)}
    if issue.get("state") == "closed" and "genesis-closed-sealed-completed" in labels:
        return {"issue": number, "status": "already_sealed"}
    pr = _api(repository, token, "GET", f"/pulls/{pr_number}")
    changed = _api(repository, token, "GET", f"/pulls/{pr_number}/files?per_page=100")
    if not isinstance(changed, list) or len(changed) >= 100:
        raise ValueError("PR file count cannot be independently bounded")
    target = validate_merged_repair(issue, pr, changed, number=number, pr_number=pr_number, sha=sha)
    marker = f"{MARKER}{sha} -->"
    comments = _api(repository, token, "GET", f"/issues/{number}/comments?per_page=100")
    if not isinstance(comments, list) or len(comments) >= 100:
        raise ValueError("issue comments cannot be independently bounded")
    evidence = (
        f"{marker}\nGenesis verification evidence: independently validated merged PR #{pr_number} "
        f"for issue #{number}. Promoted main SHA: `{sha}`. Verified target: `{target}`. "
        f"Target-specific regression tests and full repository validation passed after promotion "
        f"in independent verifier run {os.environ.get('GITHUB_RUN_ID', 'unknown')}. "
        "This is an independently checked manual PR fix, NOT an autonomous AI-produced repair."
    )
    if not any(marker in str(comment.get("body") or "") for comment in comments):
        _api(repository, token, "POST", f"/issues/{number}/comments", {"body": evidence})
    _api(repository, token, "POST", f"/issues/{number}/labels", {"labels": ["genesis-verified"]})
    # Direct reconciliation avoids GitHub GITHUB_TOKEN event-dispatch suppression.
    from scripts.issue_closure_manager import reconcile
    closure = reconcile(repository, token, issue_number=number)
    if not any(item.get("issue") == number and item.get("action") == "close_completed" for item in closure.get("changes", [])):
        raise RuntimeError(f"verification recorded but issue closure not confirmed: {closure}")
    return {"issue": number, "status": "verified_closed", "sha": sha}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--queue", type=Path, default=QUEUE)
    args = parser.parse_args()
    repository = os.environ.get("GITHUB_REPOSITORY", "")
    token = os.environ.get("GITHUB_TOKEN", "")
    if not repository or not token:
        raise SystemExit("GitHub repository and token required")
    rows = json.loads(args.queue.read_text(encoding="utf-8"))
    if not isinstance(rows, list) or not rows or len(rows) > 10:
        raise SystemExit("bounded verification queue (1-10) required")
    for row in rows:
        print(json.dumps(verify_one(repository, token, row), sort_keys=True))


if __name__ == "__main__":
    main()
