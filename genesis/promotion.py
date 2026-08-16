from __future__ import annotations

import base64
import json
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

PROTECTED_PATHS = {"GENESIS_CONSTITUTION.md", "GENESIS_BLOCK.json"}


@dataclass(frozen=True)
class SignedValidationVote:
    validator_id: str
    candidate_commit: str
    decision: str
    reason: str
    created_at: str
    signature_b64: str


def generate_validator_keypair() -> tuple[Ed25519PrivateKey, str]:
    private_key = Ed25519PrivateKey.generate()
    public_bytes = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return private_key, base64.b64encode(public_bytes).decode("ascii")


def _vote_payload(validator_id: str, candidate_commit: str, decision: str, reason: str, created_at: str) -> bytes:
    return json.dumps(
        {
            "validator_id": validator_id,
            "candidate_commit": candidate_commit,
            "decision": decision,
            "reason": reason,
            "created_at": created_at,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def make_signed_vote(
    private_key: Ed25519PrivateKey,
    validator_id: str,
    candidate_commit: str,
    decision: str,
    reason: str,
) -> SignedValidationVote:
    if decision not in {"approve", "reject"}:
        raise ValueError("decision must be approve or reject")
    created_at = datetime.now(timezone.utc).isoformat()
    payload = _vote_payload(validator_id, candidate_commit, decision, reason, created_at)
    signature = private_key.sign(payload)
    return SignedValidationVote(
        validator_id=validator_id,
        candidate_commit=candidate_commit,
        decision=decision,
        reason=reason,
        created_at=created_at,
        signature_b64=base64.b64encode(signature).decode("ascii"),
    )


def verify_vote(vote: SignedValidationVote, public_key_b64: str) -> bool:
    try:
        public_key = Ed25519PublicKey.from_public_bytes(base64.b64decode(public_key_b64))
        payload = _vote_payload(
            vote.validator_id,
            vote.candidate_commit,
            vote.decision,
            vote.reason,
            vote.created_at,
        )
        public_key.verify(base64.b64decode(vote.signature_b64), payload)
        return True
    except (ValueError, InvalidSignature):
        return False


class PromotionManager:
    """Cryptographically gated promotion of an exact candidate commit.

    A candidate may reach main only when:
    - main is an ancestor of the candidate (fast-forward only)
    - Genesis identity files are unchanged
    - the exact candidate commit has enough valid Ed25519 approvals from
      distinct trusted validator identities
    - no trusted validator submitted a valid rejection
    - the full test suite passes again at the exact candidate commit
    """

    def __init__(self, root: Path, trusted_validators: dict[str, str], min_approvals: int = 2) -> None:
        self.root = root.resolve()
        self.trusted_validators = dict(trusted_validators)
        self.min_approvals = min_approvals

    def _git(self, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
        return subprocess.run(["git", *args], cwd=self.root, text=True, capture_output=True, check=check)

    def changed_files(self, candidate_commit: str) -> list[str]:
        main = self._git("rev-parse", "main").stdout.strip()
        result = self._git("diff", "--name-only", f"{main}..{candidate_commit}")
        return [line.strip() for line in result.stdout.splitlines() if line.strip()]

    def valid_votes(self, candidate_commit: str, votes: list[SignedValidationVote]) -> list[SignedValidationVote]:
        valid: list[SignedValidationVote] = []
        seen: set[str] = set()
        for vote in votes:
            if vote.candidate_commit != candidate_commit or vote.validator_id in seen:
                continue
            public_key = self.trusted_validators.get(vote.validator_id)
            if not public_key:
                continue
            if verify_vote(vote, public_key):
                valid.append(vote)
                seen.add(vote.validator_id)
        return valid

    def validate_candidate(self, candidate_commit: str, votes: list[SignedValidationVote]) -> dict:
        main = self._git("rev-parse", "main").stdout.strip()
        ancestor = self._git("merge-base", "--is-ancestor", main, candidate_commit, check=False).returncode == 0
        changed = self.changed_files(candidate_commit) if ancestor else []
        protected_unchanged = not any(path in PROTECTED_PATHS for path in changed)
        exact_valid_votes = self.valid_votes(candidate_commit, votes)
        rejects = [v for v in exact_valid_votes if v.decision == "reject"]
        approvers = {v.validator_id for v in exact_valid_votes if v.decision == "approve"}
        return {
            "candidate_commit": candidate_commit,
            "fast_forwardable": ancestor,
            "changed_files": changed,
            "protected_unchanged": protected_unchanged,
            "valid_votes": len(exact_valid_votes),
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

    def promote(self, candidate_commit: str, votes: list[SignedValidationVote]) -> dict:
        gate = self.validate_candidate(candidate_commit, votes)
        if not gate["fast_forwardable"]:
            raise RuntimeError("candidate is not fast-forwardable from main")
        if not gate["protected_unchanged"]:
            raise RuntimeError("candidate changes protected Genesis identity files")
        if not gate["quorum_met"]:
            raise RuntimeError("cryptographic validator quorum not met or a rejection exists")
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
