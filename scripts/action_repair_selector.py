from __future__ import annotations

import argparse
import json
import subprocess

from scripts.action_failure_watchdog import decode_metadata

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


def choose_repairable_issue(issues: list[dict]) -> int | None:
    candidates: list[tuple[int, int]] = []
    for issue in issues:
        metadata = decode_metadata(str(issue.get("body") or ""))
        if not metadata:
            continue
        workflow_path = str(metadata.get("workflow_path") or "").replace("\\", "/")
        cycles = int(metadata.get("repair_cycles") or 0)
        number = int(issue.get("number") or 0)
        if not number or cycles >= MAX_REPAIR_CYCLES:
            continue
        if workflow_path in PROTECTED_ACTION_CONTROL_PATHS:
            continue
        candidates.append((cycles, number))
    if not candidates:
        return None
    candidates.sort(key=lambda item: (item[0], item[1]))
    return candidates[0][1]


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
