import json
from pathlib import Path

from scripts import embed_dashboard_status as embedder


def test_embed_dashboard_status_renders_without_status_fetch(tmp_path: Path):
    status = tmp_path / "status.json"
    page = tmp_path / "index.html"
    status.write_text(json.dumps({"generated_at": "2026-08-22T08:00:00Z", "ai_capability": 37}), encoding="utf-8")
    page.write_text(
        "<html><body><div id='updated'></div><div id='sideUpdated'></div>"
        "<script>let DATA=null;const $=s=>document.querySelector(s);function age(){return 'now'};function render(){}</script>"
        "</body></html>",
        encoding="utf-8",
    )

    embedder.embed(status, page)
    html = page.read_text(encoding="utf-8")

    assert 'id="genesisEmbeddedStatus"' in html
    assert 'window.__GENESIS_STATUS__=' in html
    assert '"ai_capability":37' in html
    assert 'embedded evidence' in html
    assert html.index('window.__GENESIS_STATUS__=') < html.index('</body>')


def test_embed_dashboard_status_is_idempotent(tmp_path: Path):
    status = tmp_path / "status.json"
    page = tmp_path / "index.html"
    status.write_text(json.dumps({"generated_at": "2026-08-22T08:00:00Z"}), encoding="utf-8")
    page.write_text("<html><body></body></html>", encoding="utf-8")

    embedder.embed(status, page)
    embedder.embed(status, page)

    assert page.read_text(encoding="utf-8").count('id="genesisEmbeddedStatus"') == 1


def test_pages_workflow_deploys_even_if_history_backfill_rejects_runtime_history():
    workflow = Path(".github/workflows/pages-status.yml").read_text(encoding="utf-8")
    assert "if ! python scripts/autonomy_history_backfill.py; then" in workflow
    assert "python scripts/embed_dashboard_status.py" in workflow
    assert workflow.index("python scripts/embed_dashboard_status.py") < workflow.index("python scripts/validate_dashboard_js.py")
