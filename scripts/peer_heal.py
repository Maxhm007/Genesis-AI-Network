#!/usr/bin/env python3
"""Genesis cross-node recovery coordinator.

A peer votes on durable recovery requests. Two distinct peer votes are required before
remote recovery is triggered. The first recovery action is deliberately conservative:
re-run the target node's own self-healing workflow. Requests remain open until a healthy
self-healing run is observed, preventing false recovery claims.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys

PREFIX = "[genesis-peer-heal]"
VOTE_PREFIX = "peer_vote:"


def gh(args: list[str], input_obj=None, allow_fail=False):
    cmd = ["gh", "api", *args]
    data = None
    if input_obj is not None:
        cmd += ["--input", "-"]
        data = json.dumps(input_obj)
    p = subprocess.run(cmd, input=data, text=True, capture_output=True)
    if p.returncode and not allow_fail:
        raise RuntimeError(p.stderr.strip() or p.stdout.strip())
    if p.returncode:
        return None
    text = p.stdout.strip()
    return json.loads(text) if text else {}


def parse_body(body: str) -> dict[str, str]:
    out = {}
    for line in body.splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            if k.strip() in {"source_node", "source_repo", "source_run_id", "source_run_url"}:
                out[k.strip()] = v.strip()
    return out


def comments(repo: str, issue: int):
    return gh([f"repos/{repo}/issues/{issue}/comments", "-f", "per_page=100"]) or []


def add_comment(repo: str, issue: int, body: str):
    gh([f"repos/{repo}/issues/{issue}/comments"], {"body": body})


def close_issue(repo: str, issue: int):
    gh([f"repos/{repo}/issues/{issue}"], {"state": "closed"})


def latest_self_heal_success(repo: str) -> bool:
    runs = gh([f"repos/{repo}/actions/workflows/self-healing.yml/runs", "-f", "per_page=5"], allow_fail=True)
    if not runs:
        return False
    for run in runs.get("workflow_runs", []):
        if run.get("status") == "completed":
            return run.get("conclusion") == "success"
    return False


def find_or_create_coordination_issue(source_repo: str, source_run_id: str, source_node: str) -> int:
    title = f"[genesis-network-repair] {source_node} run {source_run_id}"
    issues = gh([f"repos/{source_repo}/issues", "-f", "state=open", "-f", "per_page=100"]) or []
    for item in issues:
        if item.get("title") == title:
            return int(item["number"])
    item = gh([f"repos/{source_repo}/issues"], {
        "title": title,
        "body": (
            "Genesis network repair coordination.\n\n"
            f"source_node: {source_node}\nsource_run_id: {source_run_id}\n"
            "policy: self-heal first; peer recovery requires 2-of-3 quorum.\n"
        ),
    })
    return int(item["number"])


def vote_count(source_repo: str, issue_no: int) -> set[str]:
    voters = set()
    for c in comments(source_repo, issue_no):
        body = c.get("body") or ""
        m = re.search(r"peer_vote:\s*([A-Za-z0-9_.-]+)", body)
        if m:
            voters.add(m.group(1))
    return voters


def dispatch_self_heal(source_repo: str):
    return gh(
        ["--method", "POST", f"repos/{source_repo}/actions/workflows/self-healing.yml/dispatches"],
        {"ref": "main"},
        allow_fail=True,
    )


def main() -> int:
    if not (os.getenv("GH_TOKEN") or os.getenv("GITHUB_TOKEN")):
        print("GENESIS_NETWORK_TOKEN missing; peer healing cannot cross repository boundaries.")
        return 0
    node_id = os.getenv("NODE_ID", "genesis-node-0")
    own_repo = os.getenv("GITHUB_REPOSITORY") or os.getenv("NODE_REPO")
    if not own_repo:
        print("Cannot determine current repository", file=sys.stderr)
        return 1

    issues = gh([f"repos/{own_repo}/issues", "-f", "state=open", "-f", "per_page=100"]) or []
    requests = [i for i in issues if (i.get("title") or "").startswith(PREFIX)]
    if not requests:
        print("No peer recovery requests.")
        return 0

    for req in requests:
        meta = parse_body(req.get("body") or "")
        source_repo = meta.get("source_repo")
        source_run_id = meta.get("source_run_id", "unknown")
        source_node = meta.get("source_node", "unknown")
        if not source_repo:
            add_comment(own_repo, req["number"], "Invalid recovery request: missing source_repo.")
            continue

        if latest_self_heal_success(source_repo):
            add_comment(own_repo, req["number"], f"Recovery verified by {node_id}: target self-healing is healthy.")
            close_issue(own_repo, req["number"])
            continue

        coordination = find_or_create_coordination_issue(source_repo, source_run_id, source_node)
        existing = vote_count(source_repo, coordination)
        if node_id not in existing:
            add_comment(source_repo, coordination, f"{VOTE_PREFIX} {node_id}\naction: approve conservative recovery")
        voters = vote_count(source_repo, coordination)
        add_comment(own_repo, req["number"], f"{node_id} voted for recovery. quorum={len(voters)}/2")

        if len(voters) >= 2:
            result = dispatch_self_heal(source_repo)
            if result is None:
                add_comment(own_repo, req["number"], "Quorum reached, but target self-healing workflow could not be dispatched. Escalation remains open.")
            else:
                add_comment(own_repo, req["number"], "Quorum reached. Target self-healing workflow dispatched remotely; awaiting healthy verification.")
        else:
            print(f"Awaiting another peer vote for {source_repo} run {source_run_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
