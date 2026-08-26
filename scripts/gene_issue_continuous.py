from __future__ import annotations

import argparse
import json
import signal
import time

from genesis.pulse import GenePulse


STOP = False


def _stop(*_: object) -> None:
    global STOP
    STOP = True


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run one persistent Genesis Gene through the GitHub-Issue-authoritative Pulse boundary."
    )
    parser.add_argument("--gene", default="gene-node-1", help="Internal Gene logical id")
    parser.add_argument("--idle-pause", type=float, default=5.0, help="Small anti-spin pause between bounded pulses")
    parser.add_argument(
        "--authority-retry-pause",
        type=float,
        default=60.0,
        help="Backoff when GitHub Issue authority is unavailable",
    )
    args = parser.parse_args()

    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)

    while not STOP:
        result = GenePulse(__import__("pathlib").Path.cwd(), args.gene).report()
        print(json.dumps(result, sort_keys=True), flush=True)
        authority_blocked = result.get("action") in {
            "github_issue_sync_blocked",
            "github_issue_intake_blocked",
        }
        pause = args.authority_retry_pause if authority_blocked else args.idle_pause
        time.sleep(max(0.1, pause))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
