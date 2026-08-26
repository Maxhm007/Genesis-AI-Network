from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.action_failure_watchdog import decode_metadata, failure_root_fingerprint

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
MAX_REPAIR_CYCLES = 3
FAILURE_CLASS_PRIORITY = {
    "syntax": 0,
    "dependency": 1,
    "artifact": 2,
    "test": 3,
    "code": 4,
    "infrastructure": 5,
    "unknown": 6,
}


def classify_failure(body: str) -> str:
    text = str(body or "").lower()
    if any(token in text for token in ("syntax error", "here-document", "yaml parse", "mapping values are not allowed")):
        return "syntax"
    if any(token in text for token in ("modulenotfounderror", "no module named", "could not find a version that satisfies", "distribution not found")):
        return "dependency"
    if "filenotfounderror" in text or ("artifact" in text and any(token in text for token in ("not found", "missing", "could not find"))):
        return "artifact"
    if any(token in text for token in ("assertionerror", "failed tests", "pytest", "test session")):
        return "test"
    if any(token in text for token in ("name or service not known", "connection reset", "service unavailable", "timed out", "timeout")):
        return "infrastructure"
    if any(token in text for token in ("traceback", "exception", "error:")):
        return "code"
    return "unknown"


def choose_repairable_issue(issues: list[dict]) -> int | None:
    """Choose one root failure fairly.

    Every untouched root gets a turn before a retry generation can run again.
    Within the same repair generation, the lower GitHub issue number wins so
    older unresolved failures cannot be jumped by newer syntax/dependency noise.
    Validator A/B duplicates are treated as one root even before the watchdog's
    persistent deduplication pass closes duplicate issue records.
    """
    candidates: list[tuple[int, int, int, int]] = []
    seen_roots: set[str] = set()
    for issue in sorted(issues, key=lambda row: int(row.get("number") or 0)):
        body = str(issue.get("body") or "")
        metadata = decode_metadata(body)
        if not metadata:
            continue
        workflow_path = str(metadata.get("workflow_path") or "").replace("\\", "/")
        cycles = int(metadata.get("repair_cycles") or 0)
        number = int(issue.get("number") or 0)
        if not number or cycles >= MAX_REPAIR_CYCLES:
            continue
        if workflow_path in PROTECTED_ACTION_CONTROL_PATHS:
            continue
        root = str(metadata.get("root_fingerprint") or failure_root_fingerprint(metadata))
        if root in seen_roots:
            continue
        seen_roots.add(root)
        failure_class = classify_failure(body)
        candidates.append((cycles, number, FAILURE_CLASS_PRIORITY[failure_class], number))
    if not candidates:
        return None
    candidates.sort()
    return candidates[0][3]


def list_authorized_issues(repository: str) -> list[dict]:
    result = subprocess.run(
        [
            "gh",
            "issue",
            "list",
            "--repo",
            repository,
            "--state",
            "open",
            "--label",
            "genesis-action-autonomous",
            "--limit",
            "100",
            "--json",
            "number,body",
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError((result.stderr or result.stdout or "issue list failed")[-1200:])
    payload = json.loads(result.stdout or "[]")
    return list(payload) if isinstance(payload, list) else []


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", required=True)
    args = parser.parse_args()
    selected = choose_repairable_issue(list_authorized_issues(args.repository))
    print(selected or "")


if __name__ == "__main__":
    main()
