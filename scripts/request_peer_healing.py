#!/usr/bin/env python3
"""Request peer recovery when a Genesis node cannot heal itself.

Creates a durable recovery request in each configured peer repository. Peers consume
these requests through their scheduled peer-healing workflow. The request is idempotent
for a source node/run pair and contains only metadata needed to coordinate repair.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys


def gh_json(args: list[str], payload: dict | None = None) -> dict:
    cmd = ["gh", "api", *args]
    if payload is not None:
        cmd += ["--input", "-"]
    proc = subprocess.run(
        cmd,
        input=(json.dumps(payload) if payload is not None else None),
        text=True,
        capture_output=True,
    )
    if proc.returncode:
        raise RuntimeError(proc.stderr.strip() or proc.stdout.strip())
    return json.loads(proc.stdout or "{}")


def main() -> int:
    token = os.getenv("GH_TOKEN") or os.getenv("GITHUB_TOKEN")
    if not token:
        print("GENESIS_NETWORK_TOKEN is not configured; peer recovery request skipped.")
        return 0

    source_node = os.getenv("NODE_ID", "genesis-node-0")
    source_repo = os.getenv("GITHUB_REPOSITORY", "Maxhm007/Genesis-AI-Network")
    run_id = os.getenv("GITHUB_RUN_ID", "unknown")
    run_url = f"https://github.com/{source_repo}/actions/runs/{run_id}"
    peer_repos = [p.strip() for p in os.getenv("PEER_REPOS", "").split(",") if p.strip()]
    if not peer_repos:
        print("No peer repositories configured.")
        return 0

    title = f"[genesis-peer-heal] {source_node} recovery request {run_id}"
    body = (
        "Genesis peer recovery request.\n\n"
        f"source_node: {source_node}\n"
        f"source_repo: {source_repo}\n"
        f"source_run_id: {run_id}\n"
        f"source_run_url: {run_url}\n"
        "requested_action: diagnose_and_repair\n"
        "policy: self-heal-first; peer-heal-second; risky repair requires peer quorum\n"
    )

    failures = 0
    for repo in peer_repos:
        try:
            existing = gh_json([
                f"repos/{repo}/issues",
                "-f", "state=open",
                "-f", "per_page=100",
            ])
            if isinstance(existing, list) and any(i.get("title") == title for i in existing):
                print(f"Peer request already exists in {repo}")
                continue
            created = gh_json(
                [f"repos/{repo}/issues"],
                {"title": title, "body": body, "labels": ["genesis-peer-heal"]},
            )
            print(f"Requested peer recovery from {repo}: #{created.get('number')}")
        except Exception as exc:  # keep trying other peers
            failures += 1
            print(f"Failed to request recovery from {repo}: {exc}", file=sys.stderr)
    return 1 if failures == len(peer_repos) else 0


if __name__ == "__main__":
    raise SystemExit(main())
