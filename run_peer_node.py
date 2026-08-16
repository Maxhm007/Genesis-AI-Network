from __future__ import annotations

import argparse
import hashlib
import json
import signal
import time
from pathlib import Path

from genesis.peers import PeerClient, PeerStatusServer


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a lightweight Genesis peer status node")
    parser.add_argument("--node-id", required=True)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--peer", action="append", default=[])
    parser.add_argument("--cycles", type=int, default=None)
    parser.add_argument("--interval", type=float, default=2.0)
    args = parser.parse_args()

    root = Path(__file__).resolve().parent
    constitution_hash = sha256(root / "GENESIS_CONSTITUTION.md")
    block = json.loads((root / "GENESIS_BLOCK.json").read_text(encoding="utf-8"))
    expected = block["constitution"]["sha256"]
    if constitution_hash != expected:
        raise SystemExit("Genesis Constitution verification failed")

    state = {"cycles": 0, "compatible_peers": 0, "last_peer_results": []}

    def status() -> dict:
        return {
            "network": "Genesis AI Network",
            "version": "0.1.0",
            "node_id": args.node_id,
            "constitution_sha256": constitution_hash,
            "status": "awake",
            "cycles": state["cycles"],
            "compatible_peers": state["compatible_peers"],
        }

    server = PeerStatusServer(args.host, args.port, status)
    server.start()
    address = f"http://{server.address[0]}:{server.address[1]}"
    print(f"{args.node_id} awake at {address}", flush=True)

    running = True

    def stop(*_):
        nonlocal running
        running = False

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    client = PeerClient(timeout=1.5)

    try:
        while running and (args.cycles is None or state["cycles"] < args.cycles):
            state["cycles"] += 1
            results = []
            compatible = 0
            for peer in args.peer:
                record = client.probe(peer, constitution_hash)
                item = {
                    "node_id": record.node_id,
                    "url": record.url,
                    "status": record.status,
                    "constitution_sha256": record.constitution_sha256,
                }
                results.append(item)
                if record.status == "compatible":
                    compatible += 1
            state["compatible_peers"] = compatible
            state["last_peer_results"] = results
            print(json.dumps({"node": args.node_id, "cycle": state["cycles"], "peers": results}, sort_keys=True), flush=True)
            if args.cycles is None or state["cycles"] < args.cycles:
                time.sleep(args.interval)
    finally:
        server.stop()
        print(f"{args.node_id} stopped", flush=True)


if __name__ == "__main__":
    main()
