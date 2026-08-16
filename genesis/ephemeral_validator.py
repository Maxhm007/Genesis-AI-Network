from __future__ import annotations

import argparse
import base64
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

PROTECTED_PATHS = {"GENESIS_CONSTITUTION.md", "GENESIS_BLOCK.json"}


def _git(root: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=root, text=True, capture_output=True, check=check)


def _payload(vote: dict) -> bytes:
    canonical = {
        "validator_id": vote["validator_id"],
        "candidate_commit": vote["candidate_commit"],
        "decision": vote["decision"],
        "reason": vote["reason"],
        "created_at": vote["created_at"],
        "constitution_sha256": vote["constitution_sha256"],
    }
    return json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode("utf-8")


def validate(root: Path, validator_id: str, candidate_commit: str) -> dict:
    constitution_hash = hashlib.sha256((root / "GENESIS_CONSTITUTION.md").read_bytes()).hexdigest()
    block = json.loads((root / "GENESIS_BLOCK.json").read_text(encoding="utf-8"))
    expected = block["constitution"]["sha256"]
    if constitution_hash != expected:
        decision = "reject"
        reason = "local Constitution does not match Genesis Block"
    else:
        main = _git(root, "rev-parse", "main").stdout.strip()
        descendant = _git(root, "merge-base", "--is-ancestor", main, candidate_commit, check=False).returncode == 0
        if not descendant:
            decision = "reject"
            reason = "candidate is not descended from main"
        else:
            changed = _git(root, "diff", "--name-only", f"{main}..{candidate_commit}").stdout.splitlines()
            if any(path in PROTECTED_PATHS for path in changed):
                decision = "reject"
                reason = "candidate changes protected Genesis identity files"
            else:
                current = _git(root, "branch", "--show-current").stdout.strip() or "main"
                _git(root, "checkout", "--detach", candidate_commit)
                try:
                    test = subprocess.run(
                        [sys.executable, "-m", "pytest", "-q"],
                        cwd=root,
                        text=True,
                        capture_output=True,
                    )
                finally:
                    _git(root, "checkout", current)
                if test.returncode == 0:
                    decision = "approve"
                    reason = "protected files unchanged and full test suite passed"
                else:
                    decision = "reject"
                    reason = "full test suite failed"

    key = Ed25519PrivateKey.generate()
    public_raw = key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    vote = {
        "validator_id": validator_id,
        "candidate_commit": candidate_commit,
        "decision": decision,
        "reason": reason,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "constitution_sha256": constitution_hash,
    }
    vote["public_key_b64"] = base64.b64encode(public_raw).decode("ascii")
    vote["signature_b64"] = base64.b64encode(key.sign(_payload(vote))).decode("ascii")
    return vote


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--validator-id", required=True)
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    vote = validate(root, args.validator_id, args.candidate)
    Path(args.output).write_text(json.dumps(vote, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(vote, sort_keys=True))
    if vote["decision"] != "approve":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
