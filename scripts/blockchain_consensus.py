from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import urllib.request

from genesis.blockchain import BlockchainModule


PEERS = {
    "genesis-node-2": (
        "Maxhm007/Genesis-Node-2",
        "https://raw.githubusercontent.com/Maxhm007/Genesis-Node-2/main/attestation.json",
    ),
    "genesis-node-3": (
        "Maxhm007/Genesis-Node-3",
        "https://raw.githubusercontent.com/Maxhm007/Genesis-Node-3/main/attestation.json",
    ),
}


def fetch_json(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


def load_public_keys(root: Path) -> dict[str, str]:
    """Load pinned public validator keys only; private key material is never read here."""
    path = root / "config" / "gden_peer_keys.json"
    if not path.is_file():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("config/gden_peer_keys.json must contain a peer-id to public-key mapping")
    return {str(peer_id): str(public_key) for peer_id, public_key in payload.items() if str(public_key).strip()}


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    tracked_chain = root / "network" / "blockchain.jsonl"
    runtime_chain = root / "runtime" / "blockchain.jsonl"
    runtime_chain.parent.mkdir(parents=True, exist_ok=True)
    if tracked_chain.exists():
        shutil.copyfile(tracked_chain, runtime_chain)
    elif runtime_chain.exists():
        runtime_chain.unlink()

    chain = BlockchainModule(root, quorum=2)
    verification = chain.verify()
    attestations: list[dict] = []
    peer_errors: dict[str, str] = {}

    for peer_id, (_, url) in PEERS.items():
        try:
            attestations.append(fetch_json(url))
        except Exception as exc:
            peer_errors[peer_id] = f"{type(exc).__name__}: {exc}"

    trusted = {peer_id: repo for peer_id, (repo, _) in PEERS.items()}
    trusted_keys = load_public_keys(root)

    # Repository agreement remains useful evidence, but it is deliberately weaker
    # than cryptographic consensus and is never exposed as `consensus_active`.
    repository_agreement = chain.consensus_status(attestations, trusted_peers=trusted)
    consensus = chain.consensus_status(
        attestations,
        trusted_peers=trusted,
        trusted_peer_keys=trusted_keys,
    )
    report = {
        **consensus,
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "trusted_peers": trusted,
        "trusted_public_key_peers": sorted(trusted_keys),
        "peer_errors": peer_errors,
        "attestations": attestations,
        "attestation_security": "persistent-ed25519-required-for-consensus-active",
        "repository_agreement_active": bool(repository_agreement.get("consensus_active")),
        "repository_matching_peers": repository_agreement.get("matching_independent_peers", 0),
        "persistent_node_key_signatures": bool(consensus.get("consensus_active")),
        "tracked_ledger": "network/blockchain.jsonl",
    }

    runtime = root / "runtime"
    runtime.mkdir(parents=True, exist_ok=True)
    (runtime / "blockchain_consensus.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    network = root / "network"
    network.mkdir(parents=True, exist_ok=True)
    public_head = {
        "network": "gden/0.1",
        "source_repo": "Maxhm007/Genesis-AI-Network",
        "chain_valid": bool(verification.get("valid")),
        "height": verification.get("height", 0),
        "head": verification.get("head"),
        "genesis_anchor": verification.get("genesis_anchor"),
        "consensus_active": bool(consensus.get("consensus_active")),
        "matching_independent_peers": consensus.get("matching_independent_peers", 0),
        "repository_agreement_active": bool(repository_agreement.get("consensus_active")),
        "repository_matching_peers": repository_agreement.get("matching_independent_peers", 0),
        "required_quorum": consensus.get("required_quorum", 2),
        "persistent_node_key_signatures": bool(consensus.get("consensus_active")),
        "published_at": datetime.now(timezone.utc).isoformat(),
    }
    (network / "blockchain_head.json").write_text(
        json.dumps(public_head, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
