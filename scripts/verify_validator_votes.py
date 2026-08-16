from __future__ import annotations

import base64
import json
import sys
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey


def payload(vote: dict) -> bytes:
    canonical = {
        "validator_id": vote["validator_id"],
        "candidate_commit": vote["candidate_commit"],
        "decision": vote["decision"],
        "reason": vote["reason"],
        "created_at": vote["created_at"],
        "constitution_sha256": vote["constitution_sha256"],
    }
    return json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode("utf-8")


def verify(vote: dict) -> bool:
    try:
        public_key = Ed25519PublicKey.from_public_bytes(base64.b64decode(vote["public_key_b64"]))
        public_key.verify(base64.b64decode(vote["signature_b64"]), payload(vote))
        return True
    except (InvalidSignature, ValueError, KeyError):
        return False


def main() -> None:
    paths = [Path(arg) for arg in sys.argv[1:]]
    if len(paths) < 2:
        raise SystemExit("need at least two vote files")
    votes = [json.loads(path.read_text(encoding="utf-8")) for path in paths]
    commits = {v["candidate_commit"] for v in votes}
    constitutions = {v["constitution_sha256"] for v in votes}
    validator_ids = {v["validator_id"] for v in votes}
    public_keys = {v["public_key_b64"] for v in votes}
    signatures_valid = all(verify(v) for v in votes)
    approvals = [v for v in votes if v["decision"] == "approve"]

    result = {
        "votes": len(votes),
        "approvals": len(approvals),
        "distinct_validator_ids": len(validator_ids),
        "distinct_public_keys": len(public_keys),
        "same_candidate_commit": len(commits) == 1,
        "same_constitution": len(constitutions) == 1,
        "all_signatures_valid": signatures_valid,
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    passed = (
        len(approvals) >= 2
        and len(validator_ids) >= 2
        and len(public_keys) >= 2
        and len(commits) == 1
        and len(constitutions) == 1
        and signatures_valid
    )
    if not passed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
