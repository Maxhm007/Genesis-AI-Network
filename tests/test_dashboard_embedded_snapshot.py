import json
from pathlib import Path

from scripts import embed_dashboard_status as embedder


def _dashboard() -> str:
    return """<html><body><div id='updated'></div><div id='sideUpdated'></div><div id='geneSelect'></div>
<script>
let DATA=null;const $=s=>document.querySelector(s);function age(){return 'now'};function render(){window.__rendered=DATA?.ai_capability||0}
async function refreshMinute(){}
refreshMinute();setInterval(refreshMinute,60000);
</script>
</body></html>"""


def test_embed_dashboard_status_declares_payload_before_runtime_and_boots_render(tmp_path: Path):
    status = tmp_path / "status.json"
    page = tmp_path / "index.html"
    status.write_text(json.dumps({"generated_at": "2026-08-22T08:00:00Z", "ai_capability": 37}), encoding="utf-8")
    page.write_text(_dashboard(), encoding="utf-8")

    embedder.embed(status, page)
    html = page.read_text(encoding="utf-8")

    assert 'id="genesisEmbeddedStatus"' in html
    assert 'window.__GENESIS_STATUS__=' in html
    assert '"ai_capability":37' in html
    assert 'genesis-embedded-first-paint' in html
    assert 'DATA=window.__GENESIS_STATUS__' in html
    assert 'render();' in html
    assert html.index('window.__GENESIS_STATUS__=') < html.index('let DATA=null')
    assert html.index('genesis-embedded-first-paint') < html.index('refreshMinute();setInterval(refreshMinute,60000);')


def test_embed_dashboard_status_is_idempotent(tmp_path: Path):
    status = tmp_path / "status.json"
    page = tmp_path / "index.html"
    status.write_text(json.dumps({"generated_at": "2026-08-22T08:00:00Z"}), encoding="utf-8")
    page.write_text(_dashboard(), encoding="utf-8")

    embedder.embed(status, page)
    first = page.read_text(encoding="utf-8")
    embedder.embed(status, page)
    second = page.read_text(encoding="utf-8")

    assert first == second
    assert second.count('id="genesisEmbeddedStatus"') == 1
    assert second.count('genesis-embedded-first-paint') == 1


def test_embed_refuses_ambiguous_runtime_order(tmp_path: Path):
    status = tmp_path / "status.json"
    page = tmp_path / "index.html"
    status.write_text(json.dumps({"generated_at": "2026-08-22T08:00:00Z"}), encoding="utf-8")
    page.write_text("<html><body></body></html>", encoding="utf-8")

    try:
        embedder.embed(status, page)
    except RuntimeError as exc:
        assert "runtime marker" in str(exc)
    else:
        raise AssertionError("embed must reject ambiguous dashboard script ordering")


def test_pages_workflow_deploys_even_if_history_backfill_rejects_runtime_history():
    workflow = Path(".github/workflows/pages-status.yml").read_text(encoding="utf-8")
    assert "if ! python scripts/autonomy_history_backfill.py; then" in workflow
    assert "python scripts/embed_dashboard_status.py" in workflow
    assert workflow.index("python scripts/embed_dashboard_status.py") < workflow.index("python scripts/validate_dashboard_js.py")
