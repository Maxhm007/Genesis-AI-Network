#!/usr/bin/env python3
# simulation-trigger: node-2-quorum-20260818-0237
from __future__ import annotations
import json, os, subprocess, urllib.request
REQ='[genesis-recovery-request]'; VOTE='[genesis-peer-vote]'

def pub(repo,path):
    q=urllib.request.Request(f'https://api.github.com/repos/{repo}/{path}',headers={'Accept':'application/vnd.github+json','User-Agent':'genesis-peer-heal'})
    with urllib.request.urlopen(q,timeout=20) as r: return json.load(r)
def gh(ep,method='GET',payload=None):
    cmd=['gh','api','--method',method,ep]; data=None
    if payload is not None: cmd+=['--input','-']; data=json.dumps(payload)
    p=subprocess.run(cmd,input=data,text=True,capture_output=True)
    if p.returncode: raise RuntimeError(p.stderr.strip() or p.stdout.strip())
    t=p.stdout.strip(); return json.loads(t) if t else {}
def meta(body):
    o={}
    for line in (body or '').splitlines():
        if ':' in line:
            k,v=line.split(':',1); k=k.strip()
            if k in {'source_node','source_repo','source_run_id','simulation'}: o[k]=v.strip()
    return o
def unhealthy(repo):
    try: runs=pub(repo,'actions/workflows/self-healing.yml/runs?per_page=5').get('workflow_runs',[])
    except Exception: return True
    for r in runs:
        if r.get('status')=='completed': return r.get('conclusion')!='success'
    return True
def vote(own,node,target,source,run_id,simulation=False):
    title=f'{VOTE} {source} {run_id}'; issues=gh(f'repos/{own}/issues?state=open&per_page=100')
    if any(i.get('title')==title for i in issues): return
    body=f'Genesis peer recovery vote.\n\nvoter_node: {node}\ntarget_repo: {target}\nsource_node: {source}\nsource_run_id: {run_id}\nsimulation: {str(simulation).lower()}\nverdict: approve_conservative_recovery\n'
    gh(f'repos/{own}/issues',method='POST',payload={'title':title,'body':body})
def count(peers,target,source,run_id):
    title=f'{VOTE} {source} {run_id}'; n=0
    for p in peers:
        try:
            if any(i.get('title')==title and f'target_repo: {target}' in (i.get('body') or '') for i in pub(p,'issues?state=open&per_page=100')): n+=1
        except Exception: pass
    return n
def close(repo,n,msg):
    gh(f'repos/{repo}/issues/{n}/comments',method='POST',payload={'body':msg}); gh(f'repos/{repo}/issues/{n}',method='PATCH',payload={'state':'closed'})
def main():
    node=os.getenv('NODE_ID','genesis-node-0'); own=os.getenv('GITHUB_REPOSITORY') or os.getenv('NODE_REPO'); peers=[p.strip() for p in os.getenv('PEER_REPOS','').split(',') if p.strip()]
    for peer in peers:
        try: issues=pub(peer,'issues?state=open&per_page=100')
        except Exception: continue
        for req in issues:
            if not (req.get('title') or '').startswith(REQ): continue
            m=meta(req.get('body')); target=m.get('source_repo'); source=m.get('source_node'); run_id=m.get('source_run_id'); sim=m.get('simulation','false').lower()=='true'
            if target==peer and source and run_id and (sim or unhealthy(target)): vote(own,node,target,source,run_id,sim)
    for req in gh(f'repos/{own}/issues?state=open&per_page=100'):
        if not (req.get('title') or '').startswith(REQ): continue
        m=meta(req.get('body')); source=m.get('source_node'); run_id=m.get('source_run_id'); sim=m.get('simulation','false').lower()=='true'
        if not source or not run_id: continue
        if not sim and not unhealthy(own): close(own,req['number'],'Self-healing is healthy again; closing recovery request.'); continue
        n=count(peers,own,source,run_id)
        if n>=2:
            gh(f'repos/{own}/actions/workflows/self-healing.yml/dispatches',method='POST',payload={'ref':'main'})
            close(own,req['number'],f'Peer quorum reached ({n}/2). Local self-healing dispatched.' + (' Simulation passed.' if sim else ''))
        else: print(f'Awaiting peer quorum: {n}/2')
    return 0
if __name__=='__main__': raise SystemExit(main())
