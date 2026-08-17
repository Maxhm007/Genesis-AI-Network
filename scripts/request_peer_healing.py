#!/usr/bin/env python3
"""Publish a durable recovery request in this node's own repository.

Peers discover the request through the public GitHub API and publish independent votes
inside their own repositories. No shared cross-repository credential is required.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys

PREFIX = "[genesis-recovery-request]"


def gh(endpoint: str, *, method: str = "GET", payload=None):
    cmd = ["gh", "api", "--method", method, endpoint]
    data = None
    if payload is not None:
        cmd += ["--input", "-"]
        data = json.dumps(payload)
    proc = subprocess.run(cmd, input=data, text=True, capture_output=True)
    if proc.returncode:
        raise RuntimeError(proc.stderr.strip() or proc.stdout.strip())
    text = proc.stdout.strip()
    return json.loads(text) if text else {}


def main() -> int:
    if not (os.getenv("GH_TOKEN") or os.getenv("GITHUB_TOKEN")):
        print("Local GITHUB_TOKEN missing; cannot record recovery request.", file=sys.stderr)
        return 1

    source_node = os.getenv("NODE_ID", "genesis-node-0")
    source_repo = os.getenv("GITHUB_REPOSITORY", "Maxhm007/Genesis-AI-Network")
    run_id = os.getenv("GITHUB_RUN_ID", "unknown")
    title = f"{PREFIX} {source_node} {run_id}"
    body = (
        "Genesis recovery request.\n\n"
        f"source_node: {source_node}\n"
        f"source_repo: {source_repo}\n"
        f"source_run_id: {run_id}\n"
        f"source_run_url: https://github.com/{source_repo}/actions/runs/{run_id}\n"
        "requested_action: peer_validate_then_local_repair\n"
        "policy: self-heal-first; peer-heal-second; 2-of-3 quorum for peer recovery\n"
    )

    existing = gh(f"repos/{source_repo}/issues?state=open&per_page=100")
    if isinstance(existing, list) and any(i.get("title") == title for i in existing):
        print("Recovery request already recorded.")
        return 0

    created = gh(
        f"repos/{source_repo}/issues",
        method="POST",
        payload={"title": title, "body": body},
    )
    print(f"Recorded local recovery request #{created.get('number')} for peer discovery.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
