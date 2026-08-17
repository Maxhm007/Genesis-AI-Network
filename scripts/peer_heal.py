#!/usr/bin/env python3
"""Quorum-based Genesis cross-node recovery coordinator."""
from __future__ import annotations
import json, os, re, subprocess, sys

PREFIX = "[genesis-peer-heal]"
VOTE_PREFIX = "peer_vote:"


def gh(endpoint: str, *, method: str = "GET", payload=None, allow_fail: bool = False):
    cmd = ["gh", "api", "--method", method, endpoint]
    data = None
    if payload is not None:
        cmd += ["--input", "-"]
        data = json.dumps(payload)
    proc = subprocess.run(cmd, input=data, text=True, capture_output=True)
    if proc.returncode:
        if allow_fail:
            return None
        raise RuntimeError(proc.stderr.strip() or proc.stdout.strip())
    text = proc.stdout.strip()
    return json.loads(text) if text else {}


def parse_body(body: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in body.splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        if key in {"source_node", "source_repo", "source_run_id", "source_run_url"}:
            out[key] = value.strip()
    return out


def issue_comments(repo: str, number: int):
    return gh(f"repos/{repo}/issues/{number}/comments?per_page=100") or []


def comment(repo: str, number: int, body: str) -> None:
    gh(f"repos/{repo}/issues/{number}/comments", method="POST", payload={"body": body})


def close_issue(repo: str, number: int) -> None:
    gh(f"repos/{repo}/issues/{number}", method="PATCH", payload={"state": "closed"})


def latest_self_heal_success(repo: str) -> bool:
    runs = gh(f"repos/{repo}/actions/workflows/self-healing.yml/runs?per_page=5", allow_fail=True)
    if not runs:
        return False
    for run in runs.get("workflow_runs", []):
        if run.get("status") == "completed":
            return run.get("conclusion") == "success"
    return False


def coordination_issue(repo: str, run_id: str, source_node: str) -> int:
    title = f"[genesis-network-repair] {source_node} run {run_id}"
    issues = gh(f"repos/{repo}/issues?state=open&per_page=100") or []
    for item in issues:
        if item.get("title") == title:
            return int(item["number"])
    created = gh(
        f"repos/{repo}/issues",
        method="POST",
        payload={
            "title": title,
            "body": (
                "Genesis network repair coordination.\n\n"
                f"source_node: {source_node}\nsource_run_id: {run_id}\n"
                "policy: self-heal first; peer recovery requires 2-of-3 quorum.\n"
            ),
        },
    )
    return int(created["number"])


def voters(repo: str, issue_number: int) -> set[str]:
    found: set[str] = set()
    for item in issue_comments(repo, issue_number):
        match = re.search(r"peer_vote:\s*([A-Za-z0-9_.-]+)", item.get("body") or "")
        if match:
            found.add(match.group(1))
    return found


def dispatch_self_heal(repo: str) -> bool:
    result = gh(
        f"repos/{repo}/actions/workflows/self-healing.yml/dispatches",
        method="POST",
        payload={"ref": "main"},
        allow_fail=True,
    )
    return result is not None


def main() -> int:
    if not (os.getenv("GH_TOKEN") or os.getenv("GITHUB_TOKEN")):
        print("GENESIS_NETWORK_TOKEN missing; cross-node healing is disabled.", file=sys.stderr)
        return 1
    node_id = os.getenv("NODE_ID", "genesis-node-unknown")
    own_repo = os.getenv("GITHUB_REPOSITORY") or os.getenv("NODE_REPO")
    if not own_repo:
        print("Cannot determine current repository.", file=sys.stderr)
        return 1

    issues = gh(f"repos/{own_repo}/issues?state=open&per_page=100") or []
    requests = [item for item in issues if (item.get("title") or "").startswith(PREFIX)]
    if not requests:
        print("No peer recovery requests.")
        return 0

    for request in requests:
        meta = parse_body(request.get("body") or "")
        source_repo = meta.get("source_repo")
        source_run_id = meta.get("source_run_id", "unknown")
        source_node = meta.get("source_node", "unknown")
        number = int(request["number"])
        if not source_repo:
            comment(own_repo, number, "Invalid recovery request: missing source_repo.")
            continue

        if latest_self_heal_success(source_repo):
            comment(own_repo, number, f"Recovery verified by {node_id}: target self-healing is healthy.")
            close_issue(own_repo, number)
            continue

        coordination = coordination_issue(source_repo, source_run_id, source_node)
        current_voters = voters(source_repo, coordination)
        if node_id not in current_voters:
            comment(source_repo, coordination, f"{VOTE_PREFIX} {node_id}\naction: approve conservative recovery")
        current_voters = voters(source_repo, coordination)
        comment(own_repo, number, f"{node_id} voted for recovery. quorum={len(current_voters)}/2")

        if len(current_voters) >= 2:
            if dispatch_self_heal(source_repo):
                comment(own_repo, number, "Quorum reached. Target self-healing dispatched; awaiting healthy verification.")
            else:
                comment(own_repo, number, "Quorum reached, but target self-healing could not be dispatched. Escalation remains open.")
        else:
            print(f"Awaiting another peer vote for {source_repo} run {source_run_id}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
