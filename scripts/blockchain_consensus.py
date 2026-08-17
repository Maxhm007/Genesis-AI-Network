from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
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


def main() -> None:
    root = Path(__file__).resolve().parents[1]
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
    consensus = chain.consensus_status(attestations, trusted_peers=trusted)
    report = {
        **consensus,
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "trusted_peers": trusted,
        "peer_errors": peer_errors,
        "attestations": attestations,
        "attestation_security": "github-repository-authenticated",
        "persistent_node_key_signatures": False,
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
        "required_quorum": consensus.get("required_quorum", 2),
        "published_at": datetime.now(timezone.utc).isoformat(),
    }
    (network / "blockchain_head.json").write_text(
        json.dumps(public_head, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
