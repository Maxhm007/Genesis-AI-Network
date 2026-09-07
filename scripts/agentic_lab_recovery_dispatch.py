from __future__ import annotations

import json
import os
from pathlib import Path
import urllib.error
import urllib.parse
import urllib.request


ROOT = Path(__file__).resolve().parents[1]
AGENTIC_LABEL = "agentic-lab"
ACTIVE_LABELS = {
    "genesis-repair-in-progress",
    "genesis-validating",
    "genesis-working",
    "genesis-verifying",
}
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
    "scripts/secret_guard.py",
    "scripts/privileged_change_gate.py",
    "scripts/verify_validator_votes.py",
    "scripts/action_repair_guard.py",
    "scripts/issue_acceptance_guard.py",
}
MARKER = "<!-- genesis-agentic-production-recovery -->"


def request(repository: str, token: str, method: str, path: str, payload: dict | None = None):
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"https://api.github.com/repos/{repository}{path}",
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "Content-Type": "application/json",
            "User-Agent": "Genesis-AI-Network/agentic-lab-recovery",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            raw = response.read().decode("utf-8")
        return json.loads(raw) if raw.strip() else {}
    except urllib.error.HTTPError as exc:
        if method == "DELETE" and exc.code == 404:
            return {}
        detail = exc.read().decode("utf-8", errors="replace")[:1000]
        raise RuntimeError(f"GitHub HTTP {exc.code} for {method} {path}: {detail}") from exc


def labels(issue: dict) -> set[str]:
    result: set[str] = set()
    for row in issue.get("labels") or []:
        if isinstance(row, dict):
            name = str(row.get("name") or "").strip()
        else:
            name = str(row or "").strip()
        if name:
            result.add(name)
    return result


def explicit_target(body: str) -> str:
    prefix = "- **Target:** `"
    for line in str(body or "").splitlines():
        if line.startswith(prefix) and "`" in line[len(prefix):]:
            return line[len(prefix):].split("`", 1)[0].strip()
    return ""


def safe_lane(target: str) -> str:
    if not target or ".." in Path(target).parts or target in PROTECTED_TARGETS:
        return ""
    if not (ROOT / target).is_file():
        return ""
    if target.startswith("genesis/") and target.endswith(".py"):
        return "generic"
    if target.startswith("scripts/") and target.endswith(".py"):
        return "specialist"
    return ""


def all_agentic_issues(repository: str, token: str) -> list[dict]:
    encoded = urllib.parse.quote(AGENTIC_LABEL)
    rows: list[dict] = []
    for page in range(1, 101):
        batch = request(
            repository,
            token,
            "GET",
            f"/issues?state=all&labels={encoded}&sort=created&direction=asc&per_page=100&page={page}",
        )
        if not isinstance(batch, list):
            raise RuntimeError("Agentic Lab issue response was not a list")
        rows.extend(row for row in batch if isinstance(row, dict) and not row.get("pull_request"))
        if len(batch) < 100:
            break
    return rows


def remove_label(repository: str, token: str, number: int, label: str) -> None:
    request(repository, token, "DELETE", f"/issues/{number}/labels/{urllib.parse.quote(label, safe='')}")


def reserve_and_dispatch(repository: str, token: str) -> dict:
    for issue in all_agentic_issues(repository, token):
        issue_labels = labels(issue)
        if "genesis-verified" in issue_labels or issue_labels & ACTIVE_LABELS:
            continue
        target = explicit_target(str(issue.get("body") or ""))
        lane = safe_lane(target)
        if not lane:
            continue

        number = int(issue.get("number") or 0)
        if number <= 0:
            continue
        if str(issue.get("state") or "").lower() == "closed":
            request(repository, token, "PATCH", f"/issues/{number}", {"state": "open"})

        for label in ("genesis-deferred", "genesis-blocked"):
            remove_label(repository, token, number, label)
        request(repository, token, "POST", f"/issues/{number}/labels", {"labels": ["genesis-repair-in-progress"]})

        comments = request(repository, token, "GET", f"/issues/{number}/comments?per_page=100")
        if not any(MARKER in str(row.get("body") or "") for row in comments if isinstance(row, dict)):
            request(
                repository,
                token,
                "POST",
                f"/issues/{number}/comments",
                {
                    "body": (
                        f"{MARKER}\n"
                        "Agentic Lab production recovery has taken ownership after bounded-solver exhaustion. "
                        "The same authoritative Issue is being retried through the existing guarded repair, validation, "
                        "Security, and exact-promotion path. No protected-file or permission boundary is widened."
                    )
                },
            )

        workflow = "genesis-bounded-repair-worker.yml" if lane == "generic" else "genesis-specialist-repair-worker.yml"
        try:
            request(
                repository,
                token,
                "POST",
                f"/actions/workflows/{workflow}/dispatches",
                {"ref": "main", "inputs": {"issue_number": str(number)}},
            )
        except Exception:
            remove_label(repository, token, number, "genesis-repair-in-progress")
            raise

        result = {"status": "dispatched", "issue_number": number, "target": target, "lane": lane, "workflow": workflow}
        print(json.dumps(result, sort_keys=True))
        return result

    result = {"status": "idle", "reason": "no_safely_routable_agentic_issue"}
    print(json.dumps(result, sort_keys=True))
    return result


def main() -> int:
    repository = os.environ.get("GITHUB_REPOSITORY", "").strip()
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if not repository or not token:
        raise RuntimeError("GITHUB_REPOSITORY and GITHUB_TOKEN are required")
    reserve_and_dispatch(repository, token)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
