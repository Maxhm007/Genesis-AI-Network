from __future__ import annotations

import argparse
import json
import signal
import subprocess
import sys
import time
import urllib.request
from pathlib import Path


def _health(url: str) -> dict | None:
    try:
        with urllib.request.urlopen(url.rstrip('/') + '/health', timeout=1.5) as response:
            return json.loads(response.read().decode('utf-8'))
    except Exception:
        return None


def _start(root: Path, validator_id: str, port: int, key_path: Path) -> subprocess.Popen:
    return subprocess.Popen(
        [
            sys.executable,
            '-m', 'genesis.validator_service',
            '--validator-id', validator_id,
            '--port', str(port),
            '--key-path', str(key_path),
        ],
        cwd=root,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description='Run two supervised Genesis validator services.')
    parser.add_argument('--port-a', type=int, default=18871)
    parser.add_argument('--port-b', type=int, default=18872)
    parser.add_argument('--check-interval', type=float, default=2.0)
    args = parser.parse_args()

    root = Path(__file__).resolve().parent
    keys = root / 'state' / 'validator_keys'
    services = {
        'validator-a': {'port': args.port_a, 'key': keys / 'validator-a.key', 'proc': None},
        'validator-b': {'port': args.port_b, 'key': keys / 'validator-b.key', 'proc': None},
    }
    stopping = False

    def stop(*_):
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)

    for validator_id, item in services.items():
        item['proc'] = _start(root, validator_id, item['port'], item['key'])

    try:
        while not stopping:
            status = {}
            for validator_id, item in services.items():
                url = f"http://127.0.0.1:{item['port']}"
                health = _health(url)
                proc = item['proc']
                if health is None and proc.poll() is not None:
                    item['proc'] = _start(root, validator_id, item['port'], item['key'])
                    health = _health(url)
                status[validator_id] = health or {'status': 'starting_or_restarting'}
            print(json.dumps({'validators': status}, sort_keys=True), flush=True)
            time.sleep(args.check_interval)
    finally:
        for item in services.values():
            proc = item['proc']
            if proc and proc.poll() is None:
                proc.terminate()
        for item in services.values():
            proc = item['proc']
            if proc:
                try:
                    proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    proc.kill()


if __name__ == '__main__':
    main()
