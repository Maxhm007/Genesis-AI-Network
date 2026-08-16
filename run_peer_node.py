from __future__ import annotations

import argparse
import hashlib
import json
import signal
import time
from pathlib import Path

from genesis.gden import ContributionPolicy, EvolutionLedger, NodeIdentity, make_advertisement
from genesis.gden_peers import GDENPeerClient
from genesis.peers import PeerStatusServer


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run an authenticated Genesis GDEN peer node")
    parser.add_argument("--node-id", default=None, help="Optional human label only; cryptographic node ID is generated from the node key")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--peer", action="append", default=[])
    parser.add_argument("--cycles", type=int, default=None)
    parser.add_argument("--interval", type=float, default=2.0)
    parser.add_argument("--state-dir", default="state/gden")
    parser.add_argument("--max-cpu-percent", type=int, default=10)
    parser.add_argument("--max-memory-mb", type=int, default=1024)
    parser.add_argument("--max-storage-mb", type=int, default=2048)
    parser.add_argument("--allow-model-inference", action="store_true")
    args = parser.parse_args()

    root = Path(__file__).resolve().parent
    state_dir = (root / args.state_dir).resolve()
    constitution_hash = sha256(root / "GENESIS_CONSTITUTION.md")
    block = json.loads((root / "GENESIS_BLOCK.json").read_text(encoding="utf-8"))
    expected = block["constitution"]["sha256"]
    if constitution_hash != expected:
        raise SystemExit("Genesis Constitution verification failed")

    identity = NodeIdentity.load_or_create(state_dir / "node_identity.key")
    ledger = EvolutionLedger(state_dir / "evolution-ledger.jsonl")
    valid_ledger, ledger_status = ledger.verify()
    if not valid_ledger:
        raise SystemExit(f"Genesis evolution ledger verification failed: {ledger_status}")

    policy = ContributionPolicy(
        max_cpu_percent=args.max_cpu_percent,
        max_memory_mb=args.max_memory_mb,
        max_storage_mb=args.max_storage_mb,
        allow_model_inference=args.allow_model_inference,
    )
    capabilities = ["peer", "state_sync", "task_execution", "research", "validation"]
    if args.allow_model_inference:
        capabilities.append("model_inference")

    ledger.append(identity, "node_started", {
        "constitution_sha256": constitution_hash,
        "protocol_version": "gden/0.1",
        "capabilities": capabilities,
    })

    state = {
        "cycles": 0,
        "authenticated_peers": 0,
        "last_peer_results": [],
        "label": args.node_id or identity.node_id,
    }

    def status() -> dict:
        return {
            "network": "Genesis AI Network",
            "version": "0.2.0",
            "protocol_version": "gden/0.1",
            "node_id": identity.node_id,
            "label": state["label"],
            "constitution_sha256": constitution_hash,
            "status": "awake",
            "cycles": state["cycles"],
            "authenticated_peers": state["authenticated_peers"],
            "state_root": ledger.head(),
        }

    def handshake(challenge: str | None = None) -> dict:
        return make_advertisement(
            identity,
            constitution_hash,
            capabilities,
            policy,
            state_root=ledger.head(),
            # Modern GDEN clients supply an unpredictable challenge. Keeping a
            # random nonce when absent preserves diagnostic/manual compatibility,
            # but GDENPeerClient will trust only a challenge-bound response.
            nonce=challenge,
        )

    server = PeerStatusServer(args.host, args.port, status, handshake_factory=handshake)
    server.start()
    address = f"http://{server.address[0]}:{server.address[1]}"
    print(json.dumps({
        "node_id": identity.node_id,
        "label": state["label"],
        "address": address,
        "protocol": "gden/0.1",
        "state_root": ledger.head(),
    }, sort_keys=True), flush=True)

    running = True

    def stop(*_):
        nonlocal running
        running = False

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    client = GDENPeerClient(timeout=1.5)

    try:
        while running and (args.cycles is None or state["cycles"] < args.cycles):
            state["cycles"] += 1
            results = []
            authenticated = 0
            for peer in args.peer:
                record = client.probe(peer, constitution_hash)
                item = {
                    "node_id": record.node_id,
                    "url": record.url,
                    "status": record.status,
                    "constitution_sha256": record.constitution_sha256,
                    "protocol_version": record.protocol_version,
                    "capabilities": list(record.capabilities),
                    "state_root": record.state_root,
                }
                results.append(item)
                if record.status == "authenticated":
                    authenticated += 1
            state["authenticated_peers"] = authenticated
            state["last_peer_results"] = results
            print(json.dumps({"node": identity.node_id, "cycle": state["cycles"], "peers": results}, sort_keys=True), flush=True)
            if args.cycles is None or state["cycles"] < args.cycles:
                time.sleep(args.interval)
    finally:
        ledger.append(identity, "node_stopped", {"cycles": state["cycles"]})
        server.stop()
        print(f"{identity.node_id} stopped", flush=True)


if __name__ == "__main__":
    main()
