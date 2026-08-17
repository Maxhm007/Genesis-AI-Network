from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import urllib.request


def canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def github_json(url: str, token: str) -> object:
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "genesis-blockchain-recorder/1.0",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def genesis_anchor(root: Path) -> str:
    return sha256_text((root / "GENESIS_BLOCK.json").read_text(encoding="utf-8"))


def load_chain(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def block_hash(row: dict) -> str:
    material = {
        "height": row["height"],
        "timestamp": row["timestamp"],
        "previous_hash": row["previous_hash"],
        "payload_hash": row["payload_hash"],
        "payload_type": row["payload_type"],
        "producer": row["producer"],
    }
    return sha256_text(canonical_json(material))


def verify(chain: list[dict], anchor: str) -> tuple[bool, str]:
    previous = anchor
    for expected_height, row in enumerate(chain):
        if row.get("height") != expected_height:
            return False, "height discontinuity"
        if row.get("previous_hash") != previous:
            return False, "previous hash mismatch"
        if row.get("block_hash") != block_hash(row):
            return False, "block hash mismatch"
        previous = row["block_hash"]
    return True, previous


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    repo = os.environ.get("GITHUB_REPOSITORY", "Maxhm007/Genesis-AI-Network")
    token = os.environ.get("GITHUB_TOKEN", "")
    validated_sha = os.environ.get("VALIDATED_SHA", "").strip()
    validation_run_id = os.environ.get("VALIDATION_RUN_ID", "").strip()
    if not validated_sha or not token:
        raise SystemExit("VALIDATED_SHA and GITHUB_TOKEN are required")

    commit = github_json(f"https://api.github.com/repos/{repo}/commits/{validated_sha}", token)
    files = [str(item.get("filename", "")) for item in commit.get("files", [])]
    meaningful_files = [
        path for path in files
        if path not in {"network/blockchain.jsonl", "network/blockchain_head.json"}
        and not path.startswith("runtime/")
    ]
    if not meaningful_files:
        print("Skipping blockchain-generated/runtime-only commit")
        return

    chain_path = root / "network" / "blockchain.jsonl"
    chain_path.parent.mkdir(parents=True, exist_ok=True)
    chain = load_chain(chain_path)
    if any(row.get("validated_commit") == validated_sha for row in chain):
        print(f"Validated commit {validated_sha} already recorded")
        return

    anchor = genesis_anchor(root)
    valid, previous = verify(chain, anchor)
    if not valid:
        raise SystemExit(f"Refusing to append to invalid persisted chain: {previous}")

    payload = {
        "validated_commit": validated_sha,
        "validation_workflow": "Genesis Independent Validator Gate",
        "validation_run_id": validation_run_id,
        "repository": repo,
        "changed_files": meaningful_files,
        "commit_message": str(commit.get("commit", {}).get("message", ""))[:500],
    }
    row = {
        "height": len(chain),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "previous_hash": previous,
        "payload_hash": sha256_text(canonical_json(payload)),
        "payload_type": "validated_update",
        "producer": "genesis-independent-validator-gate",
        "validated_commit": validated_sha,
        "validation_run_id": validation_run_id,
        "changed_files": meaningful_files,
    }
    row["block_hash"] = block_hash(row)
    with chain_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, sort_keys=True) + "\n")

    print(json.dumps(row, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
