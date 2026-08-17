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


def _resolve_main(root: Path) -> str:
    for ref in ("main", "origin/main"):
        result = _git(root, "rev-parse", ref, check=False)
        if result.returncode == 0:
            return result.stdout.strip()
    raise RuntimeError("cannot resolve main branch")


def _candidate_fork_point(root: Path, main: str, candidate_commit: str) -> str | None:
    """Return a valid shared main-history base for a candidate.

    Concurrent candidates may start from an older main commit. A post-merge
    validator run may also validate the current main tip itself; in that case,
    compare the integrated commit against its first parent so the validator can
    verify the newly landed change instead of rejecting it as having no unique
    commits.
    """

    if candidate_commit == main:
        parent = _git(root, "rev-parse", f"{candidate_commit}^", check=False)
        if parent.returncode != 0 or not parent.stdout.strip():
            return None
        base = parent.stdout.strip()
        if _git(root, "merge-base", "--is-ancestor", base, main, check=False).returncode != 0:
            return None
        return base

    merge_base = _git(root, "merge-base", main, candidate_commit, check=False)
    if merge_base.returncode != 0 or not merge_base.stdout.strip():
        return None
    base = merge_base.stdout.strip()
    if _git(root, "merge-base", "--is-ancestor", base, main, check=False).returncode != 0:
        return None
    if _git(root, "merge-base", "--is-ancestor", base, candidate_commit, check=False).returncode != 0:
        return None
    unique = _git(root, "rev-list", "--count", f"{base}..{candidate_commit}", check=False)
    if unique.returncode != 0:
        return None
    try:
        unique_count = int(unique.stdout.strip())
    except ValueError:
        return None
    return base if unique_count > 0 else None


def _candidate_changed_paths(root: Path, base: str, candidate_commit: str) -> list[str]:
    return _git(root, "diff", "--name-only", f"{base}..{candidate_commit}").stdout.splitlines()


def _protected_paths_match_current_main(root: Path, main: str, candidate_commit: str) -> bool:
    result = _git(
        root,
        "diff",
        "--name-only",
        main,
        candidate_commit,
        "--",
        *sorted(PROTECTED_PATHS),
        check=False,
    )
    return result.returncode == 0 and not result.stdout.strip()


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
        main = _resolve_main(root)
        base = _candidate_fork_point(root, main, candidate_commit)
        if base is None:
            decision = "reject"
            reason = "candidate does not originate from main history or has no unique changes"
        elif not _protected_paths_match_current_main(root, main, candidate_commit):
            decision = "reject"
            reason = "candidate protected Genesis identity files differ from current main"
        else:
            changed = _candidate_changed_paths(root, base, candidate_commit)
            if any(path in PROTECTED_PATHS for path in changed):
                decision = "reject"
                reason = "candidate changes protected Genesis identity files"
            else:
                original = _git(root, "rev-parse", "HEAD").stdout.strip()
                _git(root, "checkout", "--detach", candidate_commit)
                try:
                    test = subprocess.run(
                        [sys.executable, "-m", "pytest", "-q"],
                        cwd=root,
                        text=True,
                        capture_output=True,
                    )
                finally:
                    _git(root, "checkout", "--detach", original)
                if test.returncode == 0:
                    decision = "approve"
                    reason = "candidate originates from main history, protected files match, and full test suite passed"
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
