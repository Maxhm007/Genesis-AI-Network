from pathlib import Path
import argparse

from genesis.node import GenesisNode


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Genesis AI Node V0.1")
    parser.add_argument("--interval", type=float, default=5.0, help="Heartbeat interval in seconds")
    parser.add_argument("--cycles", type=int, default=None, help="Optional finite cycle count for testing")
    args = parser.parse_args()

    root = Path(__file__).resolve().parent
    node = GenesisNode(root)
    node.run(interval_seconds=args.interval, cycles=args.cycles)


if __name__ == "__main__":
    main()
