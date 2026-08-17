#!/usr/bin/env python3
"""Request peer recovery when this Genesis node cannot heal itself."""
from __future__ import annotations
import json, os, subprocess, sys

def gh_json(args: list[str], payload: dict | None = None):
    cmd=["gh","api",*args]; data=None
    if payload is not None:
        cmd += ["--input","-"]; data=json.dumps(payload)
    proc=subprocess.run(cmd,input=data,text=True,capture_output=True)
    if proc.returncode: raise RuntimeError(proc.stderr.strip() or proc.stdout.strip())
    text=proc.stdout.strip(); return json.loads(text) if text else {}

def main() -> int:
    if not (os.getenv("GH_TOKEN") or os.getenv("GITHUB_TOKEN")):
        print("GENESIS_NETWORK_TOKEN is not configured; peer recovery request skipped."); return 0
    source_node=os.getenv("NODE_ID","genesis-node-0")
    source_repo=os.getenv("GITHUB_REPOSITORY","Maxhm007/Genesis-AI-Network")
    run_id=os.getenv("GITHUB_RUN_ID","unknown")
    peers=[p.strip() for p in os.getenv("PEER_REPOS","").split(",") if p.strip()]
    title=f"[genesis-peer-heal] {source_node} recovery request {run_id}"
    body=(f"Genesis peer recovery request.\n\nsource_node: {source_node}\nsource_repo: {source_repo}\n"
          f"source_run_id: {run_id}\nsource_run_url: https://github.com/{source_repo}/actions/runs/{run_id}\n"
          "requested_action: diagnose_and_repair\npolicy: self-heal-first; peer-heal-second; risky repair requires peer quorum\n")
    ok=0
    for repo in peers:
        try:
            existing=gh_json([f"repos/{repo}/issues","-f","state=open","-f","per_page=100"])
            if isinstance(existing,list) and any(i.get("title")==title for i in existing): ok+=1; continue
            gh_json([f"repos/{repo}/issues"],{"title":title,"body":body}); ok+=1
        except Exception as exc: print(f"Failed to request recovery from {repo}: {exc}",file=sys.stderr)
    return 0 if ok else 1

if __name__=="__main__": raise SystemExit(main())
