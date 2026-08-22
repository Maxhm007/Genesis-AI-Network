from pathlib import Path

from scripts.dashboard_live_minute_patch import patch_dashboard


ROOT = Path(__file__).resolve().parents[1]


def test_minute_patch_adds_live_workflow_refresh(tmp_path: Path) -> None:
    page = tmp_path / "index.html"
    page.write_text(
        '<html><body><span class="top"><div id="updated" class="updated">Loading…</div></span>'
        '<script>function loadAll(){}loadAll();setInterval(loadAll,60000);</script></body></html>',
        encoding="utf-8",
    )

    patch_dashboard(page)
    html = page.read_text(encoding="utf-8")

    assert 'id="liveMinute"' in html
    assert "actions/runs?per_page=20" in html
    assert "async function refreshMinute()" in html
    assert "setInterval(refreshMinute,60000)" in html
    assert "localStorage" in html
    assert "static evidence" not in html.lower() or "authenticated evidence" in html.lower()


def test_pages_build_applies_minute_patch_after_authenticated_status() -> None:
    workflow = (ROOT / ".github" / "workflows" / "pages-status.yml").read_text(encoding="utf-8")
    assert "python scripts/build_live_status.py" in workflow
    assert "python scripts/self_evaluation_dashboard.py" in workflow
    assert "python scripts/dashboard_live_minute_patch.py" in workflow
    assert workflow.index("python scripts/self_evaluation_dashboard.py") < workflow.index(
        "python scripts/dashboard_live_minute_patch.py"
    )
    assert "cron: '*/5 * * * *'" in workflow


def test_minute_patch_is_idempotent(tmp_path: Path) -> None:
    page = tmp_path / "index.html"
    page.write_text(
        '<div id="updated" class="updated">Loading…</div>'
        '<script>function loadAll(){}loadAll();setInterval(loadAll,60000);</script>',
        encoding="utf-8",
    )

    patch_dashboard(page)
    patch_dashboard(page)
    html = page.read_text(encoding="utf-8")

    assert html.count('id="liveMinute"') == 1
    assert html.count("const LIVE_ACTIONS_API=") == 1
    assert html.count("setInterval(refreshMinute,60000)") == 1
