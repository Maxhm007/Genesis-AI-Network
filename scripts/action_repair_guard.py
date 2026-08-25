from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path

from genesis.autonomy_guard import AutonomyGuard

ROOT = Path(__file__).resolve().parents[1]
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
    "scripts/action_repair_guard.py",
}
PERMISSION_LINE = re.compile(r"^\s*(permissions:|(?:actions|contents|issues|pull-requests|id-token|packages|deployments|security-events):\s*(?:read|write|none))\s*$", re.I)
FORBIDDEN_ADDITIONS = (
    "pull_request_target",
    "secrets: inherit",
    "runs-on: self-hosted",
    "persist-credentials: true",
)
SENSITIVE_VALIDATION_TERMS = (
    "pytest",
    "secret_guard",
    "privileged_change_gate",
    "verify_validator_votes",
    "ephemeral_validator",
)


def review_material(changed_files: list[str], diff_text: str) -> dict:
    files = sorted({str(path).replace("\\", "/") for path in changed_files if str(path).strip()})
    reasons: list[str] = []
    if not files:
        reasons.append("candidate has no changed files")
    if len(files) > 2:
        reasons.append("Action repair may change at most two material files")
    protected = sorted(set(files) & PROTECTED_ACTION_CONTROL_PATHS)
    if protected:
        reasons.append("Action repair control-plane file requires owner recovery: " + ", ".join(protected))
    if any(path in {"GENESIS_CONSTITUTION.md", "GENESIS_BLOCK.json"} for path in files):
        reasons.append("immutable Genesis identity root changed")

    added = [line[1:] for line in diff_text.splitlines() if line.startswith("+") and not line.startswith("+++")]
    removed = [line[1:] for line in diff_text.splitlines() if line.startswith("-") and not line.startswith("---")]
    if any(PERMISSION_LINE.match(line) for line in [*added, *removed]):
        reasons.append("GitHub permission edits are owner-only in autonomous Action repair")
    lowered_added = "\n".join(added).lower()
    for term in FORBIDDEN_ADDITIONS:
        if term in lowered_added:
            reasons.append(f"forbidden Action capability added: {term}")
    lowered_removed = "\n".join(removed).lower()
    for term in SENSITIVE_VALIDATION_TERMS:
        if term in lowered_removed:
            reasons.append(f"validation/security step removal requires owner review: {term}")
    if any(path.startswith(".github/") and not path.startswith(".github/workflows/") for path in files):
        reasons.append("Action repair cannot modify non-workflow GitHub configuration")
    return {"status": "pass" if not reasons else "block", "changed_files": files, "reasons": reasons}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("base_ref", nargs="?", default="origin/main")
    args = parser.parse_args()
    changed = subprocess.run(["git", "diff", "--name-only", f"{args.base_ref}...HEAD"], cwd=ROOT, text=True, capture_output=True, check=True).stdout.splitlines()
    diff = subprocess.run(["git", "diff", "--unified=0", f"{args.base_ref}...HEAD"], cwd=ROOT, text=True, capture_output=True, check=True).stdout
    material = review_material(changed, diff)
    autonomy = AutonomyGuard(ROOT).analyze(changed, diff).as_dict()
    result = {"material": material, "autonomy": autonomy}
    print(json.dumps(result, indent=2, sort_keys=True))
    if material["status"] != "pass" or autonomy["owner_escalation_required"] or not autonomy["autonomous_allowed"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
