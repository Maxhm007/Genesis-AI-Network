from __future__ import annotations

from pathlib import Path

DASHBOARD = Path("docs/status/index.html")

LIVE_PILL = '<span id="liveMinute" class="pill warn" title="60-second live GitHub workflow sync"><span class="dot warn"></span>Live 60s</span>'

LIVE_SCRIPT = r'''
const LIVE_ACTIONS_API='https://api.github.com/repos/Maxhm007/Genesis-AI-Network/actions/runs?per_page=20';
async function loadMinuteLive(){
  const el=$('#liveMinute');
  if(!el)return;
  try{
    const cacheKey='genesis-live-actions-v1',now=Date.now();
    let live=null;
    try{
      const cached=JSON.parse(localStorage.getItem(cacheKey)||'null');
      if(cached&&now-cached.at<60000)live=cached.data;
    }catch(_e){}
    if(!live){
      const r=await fetch(LIVE_ACTIONS_API,{cache:'no-store',headers:{Accept:'application/vnd.github+json'}});
      if(!r.ok)throw Error('GitHub '+r.status);
      const j=await r.json(),runs=j.workflow_runs||[];
      const active=runs.find(x=>['queued','in_progress','waiting','requested','pending'].includes(String(x.status||'')));
      const relevant=runs.find(x=>/Gene Pulse|Autonomy|Self Healing|Proactive Development|Genesis Live Status Pages/i.test(String(x.name||'')))||runs[0]||null;
      live={
        active:active?{name:active.name,status:active.status,updated_at:active.updated_at,url:active.html_url}:null,
        latest:relevant?{name:relevant.name,status:relevant.status,conclusion:relevant.conclusion,updated_at:relevant.updated_at,url:relevant.html_url}:null,
        fetched_at:new Date().toISOString()
      };
      try{localStorage.setItem(cacheKey,JSON.stringify({at:now,data:live}))}catch(_e){}
    }
    const current=live.active||live.latest,c=live.active?'good':'warn';
    el.className='pill '+c;
    el.innerHTML=`<span class="dot ${c}"></span>Live 60s · ${live.active?'working':'idle'}`;
    el.title=`60-second live GitHub workflow sync · ${current?.name||'no run'} · ${current?.status||current?.conclusion||'unknown'} · ${age(live.fetched_at)}`;
    if(current&&current.url)el.onclick=()=>window.open(current.url,'_blank','noopener');
  }catch(e){
    el.className='pill warn';
    el.innerHTML='<span class="dot warn"></span>Live 60s · fallback';
    el.title='Minute live sync unavailable; authenticated evidence snapshot continues on the GitHub scheduler.';
  }
}
async function refreshMinute(){await loadAll();await loadMinuteLive()}
'''


def patch_dashboard(path: Path = DASHBOARD) -> None:
    if not path.is_file():
        return
    html = path.read_text(encoding="utf-8")

    if 'id="liveMinute"' not in html:
        marker = '<div id="updated" class="updated">Loading…</div>'
        if marker not in html:
            raise RuntimeError("Dashboard update marker not found; refusing blind minute-refresh patch")
        html = html.replace(marker, LIVE_PILL + marker, 1)

    old_boot = 'loadAll();setInterval(loadAll,60000);'
    new_boot = 'refreshMinute();setInterval(refreshMinute,60000);'
    if 'const LIVE_ACTIONS_API=' not in html:
        if old_boot not in html:
            raise RuntimeError("Dashboard 60-second boot marker not found; refusing blind minute-refresh patch")
        html = html.replace(old_boot, LIVE_SCRIPT + new_boot, 1)
    elif new_boot not in html:
        html = html.replace(old_boot, new_boot, 1)

    path.write_text(html, encoding="utf-8")


if __name__ == "__main__":
    patch_dashboard()
