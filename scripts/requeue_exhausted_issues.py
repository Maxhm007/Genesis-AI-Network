from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import urllib.error
import urllib.parse
import urllib.request


ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "runtime"
EVIDENCE_PATH = RUNTIME / "exhausted_issue_requeue.json"
ENGINE_PATHS = (
    "genesis/coding.py",
    "genesis/compact_edit_budget.py",
    ".github/workflows/genesis-bounded-repair-worker.yml",
    "scripts/github_issue_autorepair.py",
    "genesis/learned_capabilities.py",
)
ACTIVE_LABELS = {
    "genesis-claimed",
    "genesis-working",
    "genesis-verifying",
    "genesis-repair-in-progress",
    "genesis-validating",
    "genesis-priority-claim",
}
EXHAUSTED_LABELS = {"genesis-solver-exhausted", "genesis-priority-exhausted"}
INFRASTRUCTURE_BLOCKED_LABEL = "genesis-infrastructure-blocked"
GENERATION_RETRY_LABELS = EXHAUSTED_LABELS | {INFRASTRUCTURE_BLOCKED_LABEL}
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
}
MEASUREMENT_PHRASES = (
    "post-promotion benchmark",
    "post-promotion remeasurement",
    "benchmark re-measurement",
    "benchmark remeasurement",
    "measured score improves",
    "same comparable benchmark",
)
TARGET_RE = re.compile(r"^- \*\*Target:\*\* `([^`]+)`", re.MULTILINE)
OLD_ATTEMPT_RE = re.compile(r"<!-- genesis-solver-attempt:\d+ -->")
PRIORITY_ATTEMPT_RE = re.compile(r"<!-- genesis-priority-solver-attempt:\d+ -->")


def engine_generation(root: Path = ROOT) -> str:
    digest = hashlib.sha256()
    for relative in ENGINE_PATHS:
        path = root / relative
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()[:20]


def issue_labels(issue: dict) -> set[str]:
    result: set[str] = set()
    for row in issue.get("labels") or []:
        if isinstance(row, dict):
            name = str(row.get("name") or "").strip()
        else:
            name = str(row or "").strip()
        if name:
            result.add(name)
    return result


def _eligible_retry_target(issue: dict, root: Path) -> tuple[bool, str]:
    labels = issue_labels(issue)
    if labels & ACTIVE_LABELS:
        return False, "active"

    title = str(issue.get("title") or "").strip()
    body = str(issue.get("body") or "")
    lower_title = title.lower()
    lower_body = body.lower()

    if lower_title.startswith(("genesis chat:", "[genesis hourly report]", "[genesis gene chat]")):
        return False, "persistent_channel"
    if "persistent github-native reporting channel" in lower_body:
        return False, "persistent_channel"
    if "external-authority / independent-secret provisioning blocker" in lower_body:
        return False, "external_authority"
    if lower_title.startswith(("[genesis escalation] ai capability below target", "[genesis ops] ai capability below target")):
        return False, "umbrella_state"
    if lower_title.startswith("genesis model lab:"):
        return False, "umbrella_state"
    if any(phrase in lower_body for phrase in MEASUREMENT_PHRASES):
        return False, "measurement_lane"

    match = TARGET_RE.search(body)
    target = match.group(1).strip() if match else ""
    if not target.startswith("genesis/") or not target.endswith(".py") or ".." in target:
        return False, "no_safe_target"
    if target in PROTECTED_TARGETS:
        return False, "protected_target"
    if not (root / target).is_file():
        return False, "missing_target"
    return True, target


def eligible_exhausted_issue(issue: dict, root: Path = ROOT) -> tuple[bool, str]:
    if not issue_labels(issue) & EXHAUSTED_LABELS:
        return False, "not_exhausted"
    return _eligible_retry_target(issue, root)


def eligible_generation_retry_issue(issue: dict, root: Path = ROOT) -> tuple[bool, str]:
    if not issue_labels(issue) & GENERATION_RETRY_LABELS:
        return False, "not_generation_blocked"
    return _eligible_retry_target(issue, root)


def reset_attempt_status(body: str) -> str:
    body = OLD_ATTEMPT_RE.sub("<!-- genesis-solver-attempt:0 -->", str(body or ""), count=1)
    body = PRIORITY_ATTEMPT_RE.sub("<!-- genesis-priority-solver-attempt:0 -->", body, count=1)
    return body


def _request(repository: str, token: str, method: str, path: str, payload: dict | None = None):
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        f"https://api.github.com/repos/{repository}{path}",
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "Content-Type": "application/json",
            "User-Agent": "Genesis-AI-Network/exhausted-issue-requeue",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = response.read().decode("utf-8")
        return json.loads(raw) if raw.strip() else {}
    except urllib.error.HTTPError as exc:
        if method == "DELETE" and exc.code == 404:
            return {}
        detail = exc.read().decode("utf-8", errors="replace")[:1000]
        raise RuntimeError(f"GitHub HTTP {exc.code} for {method} {path}: {detail}") from exc


def _open_issues(repository: str, token: str) -> list[dict]:
    rows: list[dict] = []
    for page in range(1, 101):
        batch = _request(repository, token, "GET", f"/issues?state=open&sort=created&direction=asc&per_page=100&page={page}")
        if not isinstance(batch, list):
            raise RuntimeError("GitHub open-Issue response was not a list")
        rows.extend(row for row in batch if isinstance(row, dict) and not row.get("pull_request"))
        if len(batch) < 100:
            break
    return rows


def run(repository: str, token: str, root: Path = ROOT, limit: int = 5) -> dict:
    generation = engine_generation(root)
    marker = f"<!-- genesis-requeue-engine:{generation} -->"
    result = {
        "status": "ok",
        "engine_generation": generation,
        "released": [],
        "skipped_same_generation": [],
        "skipped": [],
    }

    for issue in _open_issues(repository, token):
        if len(result["released"]) >= max(1, limit):
            break
        number = int(issue.get("number") or 0)
        labels = issue_labels(issue)
        eligible, reason = eligible_generation_retry_issue(issue, root)
        if not eligible:
            if labels & GENERATION_RETRY_LABELS:
                result["skipped"].append({"issue": number, "reason": reason})
            continue

        comments = _request(repository, token, "GET", f"/issues/{number}/comments?per_page=100") or []
        if any(str(row.get("body") or "").startswith(marker) for row in comments if isinstance(row, dict)):
            result["skipped_same_generation"].append(number)
            continue

        for row in comments:
            if not isinstance(row, dict):
                continue
            body = str(row.get("body") or "")
            if body.startswith("<!-- genesis-oldest-real-issue-solver -->") or body.startswith("<!-- genesis-priority-issue-solver -->"):
                reset = reset_attempt_status(body)
                if reset != body:
                    _request(repository, token, "PATCH", f"/issues/comments/{row['id']}", {"body": reset})

        for label in (
            "genesis-solver-exhausted",
            "genesis-priority-exhausted",
            "genesis-blocked",
            INFRASTRUCTURE_BLOCKED_LABEL,
        ):
            encoded = urllib.parse.quote(label, safe="")
            _request(repository, token, "DELETE", f"/issues/{number}/labels/{encoded}")

        _request(
            repository,
            token,
            "POST",
            f"/issues/{number}/comments",
            {
                "body": (
                    marker
                    + "\nGenesis repair capability changed. This previously exhausted or infrastructure-blocked Issue is released for one new bounded solver generation. "
                    + f"Engine generation: `{generation}`. Existing safety, target, validation and attempt limits remain unchanged."
                )
            },
        )
        result["released"].append({"issue": number, "target": reason})

    RUNTIME.mkdir(parents=True, exist_ok=True)
    EVIDENCE_PATH.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result


def main() -> None:
    repository = os.environ.get("GITHUB_REPOSITORY", "").strip()
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if not repository or not token:
        raise SystemExit("GITHUB_REPOSITORY and GITHUB_TOKEN are required")
    limit = int(os.environ.get("GENESIS_EXHAUSTED_REQUEUE_LIMIT", "5"))
    print(json.dumps(run(repository, token, limit=limit), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
