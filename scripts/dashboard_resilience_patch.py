from __future__ import annotations

from pathlib import Path

DASHBOARD = Path("docs/status/index.html")

OLD_LOAD = "async function loadAll(){try{const r=await fetch('./status.json?ts='+Date.now(),{cache:'no-store'});if(!r.ok)throw Error('status '+r.status);DATA=await r.json();const txt=`Snapshot ${age(DATA.generated_at)} · report ${age(DATA.hourly_report?.updated_at||DATA.hourly_report?.created_at)}`;$('#updated').textContent=txt;$('#sideUpdated').textContent=txt;render()}catch(e){$('#updated').textContent='Snapshot unavailable: '+e.message;$('#sideUpdated').textContent='Snapshot unavailable'}}"

NEW_LOAD = r"""let statusLoading=false;
async function loadAll(){
  if(statusLoading)return;
  statusLoading=true;
  const controller=new AbortController();
  const timer=setTimeout(()=>controller.abort(),8000);
  try{
    const r=await fetch('./status.json?ts='+Date.now(),{cache:'no-store',signal:controller.signal});
    if(!r.ok)throw Error('status '+r.status);
    DATA=await r.json();
    const txt=`Snapshot ${age(DATA.generated_at)} · report ${age(DATA.hourly_report?.updated_at||DATA.hourly_report?.created_at)}`;
    $('#updated').textContent=txt;
    $('#sideUpdated').textContent=txt;
    render();
  }catch(e){
    const reason=e&&e.name==='AbortError'?'timed out after 8s':(e&&e.message?e.message:'unknown error');
    $('#updated').textContent='Snapshot unavailable: '+reason;
    $('#sideUpdated').textContent='Snapshot unavailable';
    if(!DATA){
      $('#heroTitle').textContent='Dashboard data unavailable';
      $('#heroText').textContent='The page loaded, but status.json did not respond. Tap Refresh to retry.';
    }
  }finally{
    clearTimeout(timer);
    statusLoading=false;
  }
}"""


def patch_dashboard(path: Path = DASHBOARD) -> None:
    if not path.is_file():
        return
    html = path.read_text(encoding="utf-8")
    if "timed out after 8s" not in html:
        if OLD_LOAD not in html:
            raise RuntimeError("Dashboard loadAll marker not found; refusing blind resilience patch")
        html = html.replace(OLD_LOAD, NEW_LOAD, 1)

    old_minute = "async function refreshMinute(){await loadAll();await loadMinuteLive()}"
    new_minute = "async function refreshMinute(){await Promise.allSettled([loadAll(),loadMinuteLive()])}"
    if old_minute in html:
        html = html.replace(old_minute, new_minute, 1)
    elif "Promise.allSettled([loadAll(),loadMinuteLive()])" not in html:
        raise RuntimeError("Minute refresh marker not found; refusing blind resilience patch")

    path.write_text(html, encoding="utf-8")


if __name__ == "__main__":
    patch_dashboard()
