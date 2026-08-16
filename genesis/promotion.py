from __future__ import annotations

import hashlib
import json
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

PROTECTED_PATHS = {"GENESIS_CONSTITUTION.md", "GENESIS_BLOCK.json"}


@dataclass(frozen=True)
class ValidationVote:
    validator_id: str
    candidate_commit: str
    decision: str
    reason: str
    created_at: str
    vote_hash: str


def make_vote(validator_id: str, candidate_commit: str, decision: str, reason: str) -> ValidationVote:
    if decision not in {"approve", "reject"}:
        raise ValueError("decision must be approve or reject")
    created_at = datetime.now(timezone.utc).isoformat()
    payload = json.dumps(
        {
            "validator_id": validator_id,
            "candidate_commit": candidate_commit,
            "decision": decision,
            "reason": reason,
            "created_at": created_at,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return ValidationVote(
        validator_id=validator_id,
        candidate_commit=candidate_commit,
        decision=decision,
        reason=reason,
        created_at=created_at,
        vote_hash=hashlib.sha256(payload.encode("utf-8")).hexdigest(),
    )


class PromotionManager:
    """Promote a candidate only after independent validation and re-testing.

    Promotion is deliberately strict:
    - candidate must be a descendant of main (fast-forwardable)
    - protected paths must be unchanged
    - full tests must pass at candidate commit
    - at least `min_approvals` distinct validators must approve exact commit
    - any rejection blocks promotion
    - promotion uses git merge --ff-only
    """

    def __init__(self, root: Path, min_approvals: int = 2) -> None:
        self.root = root.resolve()
        self.min_approvals = min_approvals

    def _git(self, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
        return subprocess.run(["git", *args], cwd=self.root, text=True, capture_output=True, check=check)

    def changed_files(self, candidate_commit: str) -> list[str]:
        main = self._git("rev-parse", "main").stdout.strip()
        result = self._git("diff", "--name-only", f"{main}..{candidate_commit}")
        return [line.strip() for line in result.stdout.splitlines() if line.strip()]

    def validate_candidate(self, candidate_commit: str, votes: list[ValidationVote]) -> dict:
        main = self._git("rev-parse", "main").stdout.strip()
        ancestor = self._git("merge-base", "--is-ancestor", main, candidate_commit, check=False).returncode == 0
        changed = self.changed_files(candidate_commit) if ancestor else []
        protected_unchanged = not any(path in PROTECTED_PATHS for path in changed)

        exact_votes = [v for v in votes if v.candidate_commit == candidate_commit]
        rejects = [v for v in exact_votes if v.decision == "reject"]
        approvers = {v.validator_id for v in exact_votes if v.decision == "approve"}

        return {
            "candidate_commit": candidate_commit,
            "fast_forwardable": ancestor,
            "changed_files": changed,
            "protected_unchanged": protected_unchanged,
            "approvals": len(approvers),
            "rejects": len(rejects),
            "quorum_met": len(approvers) >= self.min_approvals and not rejects,
        }

    def run_tests_at_candidate(self, candidate_commit: str) -> tuple[bool, str]:
        current = self._git("branch", "--show-current").stdout.strip()
        self._git("checkout", "--detach", candidate_commit)
        try:
            test = subprocess.run(
                ["python", "-m", "pytest", "-q"],
                cwd=self.root,
                text=True,
                capture_output=True,
            )
            return test.returncode == 0, (test.stdout + "\n" + test.stderr)[-8000:]
        finally:
            self._git("checkout", current or "main")

    def promote(self, candidate_commit: str, votes: list[ValidationVote]) -> dict:
        gate = self.validate_candidate(candidate_commit, votes)
        if not gate["fast_forwardable"]:
            raise RuntimeError("candidate is not fast-forwardable from main")
        if not gate["protected_unchanged"]:
            raise RuntimeError("candidate changes protected Genesis identity files")
        if not gate["quorum_met"]:
            raise RuntimeError("validator quorum not met or a rejection exists")

        tests_passed, test_output = self.run_tests_at_candidate(candidate_commit)
        if not tests_passed:
            raise RuntimeError("candidate failed promotion test suite\n" + test_output)

        self._git("checkout", "main")
        before = self._git("rev-parse", "main").stdout.strip()
        self._git("merge", "--ff-only", candidate_commit)
        after = self._git("rev-parse", "main").stdout.strip()
        if after != candidate_commit:
            raise RuntimeError("promotion did not land exact validated commit")
        return {
            **gate,
            "tests_passed": True,
            "promoted": True,
            "main_before": before,
            "main_after": after,
        }
