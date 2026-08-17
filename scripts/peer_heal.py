#!/usr/bin/env python3
"""Tokenless cross-node healing coordinator for public Genesis repositories."""
from __future__ import annotations
import json, os, re, subprocess, urllib.request
REQ='[genesis-recovery-request]'; VOTE='[genesis-peer-vote]'

def public_issues(repo):
    url=f'https://api.github.com/repos/{repo}/issues?state=open&per_page=100'
    req=urllib.request.Request(url,headers={'Accept':'application/vnd.github+json','User-Agent':'genesis-peer-heal'})
    with urllib.request.urlopen(req,timeout=20) as r: return json.load(r)

def gh(endpoint,method='GET',payload=None):
    cmd=['gh','api','--method',method,endpoint]; data=None
    if payload is not None: cmd += ['--input','-']; data=json.dumps(payload)
    p=subprocess.run(cmd,input=data,text=True,capture_output=True)
    if p.returncode: raise RuntimeError(p.stderr.strip() or p.stdout.strip())
    t=p.stdout.strip(); return json.loads(t) if t else {}

def meta(body):
    out={}
    for line in (body or '').splitlines():
        if ':' in line:
            k,v=line.split(':',1); k=k.strip()
            if k in {'source_node','source_repo','source_run_id'}: out[k]=v.strip()
    return out

def latest_failed(repo):
    url=f'https://api.github.com/repos/{repo}/actions/workflows/self-healing.yml/runs?per_page=5'
    req=urllib.request.Request(url,headers={'Accept':'application/vnd.github+json','User-Agent':'genesis-peer-heal'})
    try:
        with urllib.request.urlopen(req,timeout=20) as r: runs=json.load(r).get('workflow_runs',[])
    except Exception: return True
    for run in runs:
        if run.get('status')=='completed': return run.get('conclusion')!='success'
    return True

def ensure_vote(own_repo,node,source_repo,source_node,run_id):
    title=f'{VOTE} {source_node} {run_id}'
    own=gh(f'repos/{own_repo}/issues?state=open&per_page=100')
    if any(i.get('title')==title for i in own): return
    body=f'Genesis peer recovery vote.\n\nvoter_node: {node}\ntarget_repo: {source_repo}\nsource_node: {source_node}\nsource_run_id: {run_id}\nverdict: approve_conservative_recovery\n'
    gh(f'repos/{own_repo}/issues',method='POST',payload={'title':title,'body':body})

def vote_count(peers,source_repo,source_node,run_id):
    title=f'{VOTE} {source_node} {run_id}'; voters=set()
    for peer in peers:
        try:
            for i in public_issues(peer):
                if i.get('title')==title and f'target_repo: {source_repo}' in (i.get('body') or ''): voters.add(peer)
        except Exception: pass
    return len(voters)

def close_issue(repo,n,body):
    gh(f'repos/{repo}/issues/{n}/comments',method='POST',payload={'body':body})
    gh(f'repos/{repo}/issues/{n}',method='PATCH',payload={'state':'closed'})

def dispatch_local(repo):
    gh(f'repos/{repo}/actions/workflows/self-healing.yml/dispatches',method='POST',payload={'ref':'main'})

def main():
    if not (os.getenv('GH_TOKEN') or os.getenv('GITHUB_TOKEN')): raise SystemExit('local GITHUB_TOKEN missing')
    node=os.getenv('NODE_ID','genesis-node-0'); own=os.getenv('GITHUB_REPOSITORY') or os.getenv('NODE_REPO')
    peers=[p.strip() for p in os.getenv('PEER_REPOS','').split(',') if p.strip()]
    # Validate peer failures and publish votes only in this node's own repo.
    for peer in peers:
        try: issues=public_issues(peer)
        except Exception: continue
        for req in issues:
            if not (req.get('title') or '').startswith(REQ): continue
            m=meta(req.get('body')); source_repo=m.get('source_repo'); source_node=m.get('source_node'); run_id=m.get('source_run_id')
            if source_repo!=peer or not source_node or not run_id: continue
            if latest_failed(source_repo): ensure_vote(own,node,source_repo,source_node,run_id)
    # For this node's own recovery requests, require both configured peers to vote.
    own_issues=gh(f'repos/{own}/issues?state=open&per_page=100')
    for req in own_issues:
        if not (req.get('title') or '').startswith(REQ): continue
        m=meta(req.get('body')); run_id=m.get('source_run_id'); source_node=m.get('source_node')
        if not run_id or not source_node: continue
        if not latest_failed(own):
            close_issue(own,req['number'],'Self-healing is healthy again; closing recovery request.')
            continue
        votes=vote_count(peers,own,source_node,run_id)
        if votes>=2:
            dispatch_local(own)
            close_issue(own,req['number'],f'Peer quorum reached ({votes}/2). Local self-healing dispatched.')
        else:
            print(f'Awaiting peer quorum for {source_node} run {run_id}: {votes}/2')
    return 0
if __name__=='__main__': raise SystemExit(main())
