from pathlib import Path

from scripts import dashboard_resilience_patch as resilience
from scripts import validate_dashboard_js as validator


def _sample_dashboard() -> str:
    return """<html><body><div id='updated'></div><div id='sideUpdated'></div><div id='heroTitle'></div><div id='heroText'></div><script>
let DATA=null;const $=s=>document.querySelector(s);function age(){return 'now'};function render(){}
async function loadAll(){try{const r=await fetch('./status.json?ts='+Date.now(),{cache:'no-store'});if(!r.ok)throw Error('status '+r.status);DATA=await r.json();const txt=`Snapshot ${age(DATA.generated_at)} · report ${age(DATA.hourly_report?.updated_at||DATA.hourly_report?.created_at)}`;$('#updated').textContent=txt;$('#sideUpdated').textContent=txt;render()}catch(e){$('#updated').textContent='Snapshot unavailable: '+e.message;$('#sideUpdated').textContent='Snapshot unavailable'}}
async function loadMinuteLive(){}
async function refreshMinute(){await loadAll();await loadMinuteLive()}
</script></body></html>"""


def test_resilience_patch_adds_timeout_and_parallel_minute_refresh(tmp_path: Path):
    page = tmp_path / "index.html"
    page.write_text(_sample_dashboard(), encoding="utf-8")
    resilience.patch_dashboard(page)
    html = page.read_text(encoding="utf-8")
    assert "AbortController" in html
    assert "timed out after 8s" in html
    assert "Promise.allSettled([loadAll(),loadMinuteLive()])" in html
    assert "Dashboard data unavailable" in html


def test_resilience_patch_is_idempotent(tmp_path: Path):
    page = tmp_path / "index.html"
    page.write_text(_sample_dashboard(), encoding="utf-8")
    resilience.patch_dashboard(page)
    first = page.read_text(encoding="utf-8")
    resilience.patch_dashboard(page)
    second = page.read_text(encoding="utf-8")
    assert first == second
    assert second.count("timed out after 8s") == 1


def test_inline_script_extractor_ignores_external_scripts():
    html = "<script src='external.js'></script><script>const x=1;</script>"
    assert validator.inline_scripts(html) == ["const x=1;"]


def test_pages_workflow_runs_resilience_and_final_js_validation():
    workflow = Path(".github/workflows/pages-status.yml").read_text(encoding="utf-8")
    assert "python scripts/dashboard_resilience_patch.py" in workflow
    assert "python scripts/validate_dashboard_js.py" in workflow
    assert "fetch-depth: 0" in workflow
