from __future__ import annotations

import argparse
import base64
import json
import subprocess
import sys
from dataclasses import dataclass

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


PRIMARY_REPO = "Maxhm007/Genesis-AI-Network"
NODES = {
    "genesis-node-2": "Maxhm007/Genesis-Node-2",
    "genesis-node-3": "Maxhm007/Genesis-Node-3",
}
SECRET_NAME = "GENESIS_NODE_PRIVATE_KEY_PEM"
REGISTRY_PATH = "config/gden_peer_keys.json"


@dataclass(frozen=True)
class NodeIdentity:
    peer_id: str
    repository: str
    private_pem: str
    public_key_b64: str


def generate_identity(peer_id: str, repository: str) -> NodeIdentity:
    private = Ed25519PrivateKey.generate()
    private_pem = private.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("ascii")
    public_raw = private.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return NodeIdentity(peer_id, repository, private_pem, base64.b64encode(public_raw).decode("ascii"))


def _run_gh(args: list[str], *, stdin_text: str | None = None, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["gh", *args], input=stdin_text, text=True, capture_output=True, check=check)


def require_gh_auth() -> None:
    try:
        result = _run_gh(["auth", "status"], check=False)
    except FileNotFoundError as exc:
        raise RuntimeError("GitHub CLI `gh` is required") from exc
    if result.returncode != 0:
        raise RuntimeError("GitHub CLI is not authenticated; run `gh auth login` first")


def put_registry(keys: dict[str, str]) -> None:
    payload_text = json.dumps(keys, indent=2, sort_keys=True) + "\n"
    encoded = base64.b64encode(payload_text.encode("utf-8")).decode("ascii")
    lookup = _run_gh(["api", f"repos/{PRIMARY_REPO}/contents/{REGISTRY_PATH}"], check=False)
    args = [
        "api",
        f"repos/{PRIMARY_REPO}/contents/{REGISTRY_PATH}",
        "--method", "PUT",
        "-f", "message=Pin persistent GDEN validator public keys",
        "-f", f"content={encoded}",
    ]
    if lookup.returncode == 0:
        current = json.loads(lookup.stdout)
        sha = str(current.get("sha", "")).strip()
        if sha:
            args.extend(["-f", f"sha={sha}"])
    result = _run_gh(args, check=False)
    if result.returncode != 0:
        raise RuntimeError(f"failed to update {REGISTRY_PATH}: {result.stderr.strip()}")


def set_private_secret(identity: NodeIdentity) -> None:
    result = _run_gh(
        ["secret", "set", SECRET_NAME, "--repo", identity.repository],
        stdin_text=identity.private_pem,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"failed to set {SECRET_NAME} for {identity.repository}: {result.stderr.strip()}")


def trigger_attestation(repository: str) -> None:
    result = _run_gh(["workflow", "run", "attest.yml", "--repo", repository], check=False)
    if result.returncode != 0:
        raise RuntimeError(f"failed to trigger attestation for {repository}: {result.stderr.strip()}")


def provision(*, dry_run: bool = False) -> dict[str, str]:
    identities = [generate_identity(peer_id, repo) for peer_id, repo in NODES.items()]
    registry = {identity.peer_id: identity.public_key_b64 for identity in identities}
    if dry_run:
        return registry
    require_gh_auth()
    for identity in identities:
        set_private_secret(identity)
    put_registry(registry)
    for identity in identities:
        trigger_attestation(identity.repository)
    return registry


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Provision persistent Ed25519 identities for GDEN validator nodes without storing signing material in Git.")
    parser.add_argument("--dry-run", action="store_true", help="generate public keys only; make no GitHub changes")
    args = parser.parse_args(argv)
    try:
        registry = provision(dry_run=args.dry_run)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(json.dumps({"peers": sorted(registry), "registry": REGISTRY_PATH, "dry_run": args.dry_run}, indent=2))
    if not args.dry_run:
        print("Persistent identities provisioned and signed-attestation workflows dispatched.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
