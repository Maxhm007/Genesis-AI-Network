from pathlib import Path

from scripts import dashboard_navigation_fallback as nav


def _page() -> str:
    return '''<!doctype html><html><head><style>.view{display:none}.view.active{display:block}.nav button{color:#fff}</style></head><body>
<nav class="nav"><button class="active" data-view="overview">Overview</button><button data-view="issues">Issues</button><button data-view="tasks">Tasks</button></nav>
<section class="view active" id="view-overview">Overview data</section><section class="view" id="view-issues">Issues data</section><section class="view" id="view-tasks">Tasks data</section>
<script>function switchView(v){}document.querySelectorAll('.nav button').forEach(b=>b.onclick=()=>switchView(b.dataset.view));document.querySelectorAll('.nav button').forEach(x=>x.classList.toggle('active',false));</script>
</body></html>'''


def test_navigation_fallback_converts_buttons_to_hash_links(tmp_path: Path):
    page = tmp_path / "index.html"
    page.write_text(_page(), encoding="utf-8")
    nav.patch_navigation(page)
    html = page.read_text(encoding="utf-8")
    assert '<a class="active" data-view="overview" href="#view-overview">Overview</a>' in html
    assert 'data-view="issues" href="#view-issues"' in html
    assert 'data-view="tasks" href="#view-tasks"' in html
    assert 'genesis-no-js-navigation' in html
    assert '.view:target{display:block}' in html
    assert "document.querySelectorAll('.nav [data-view]')" in html


def test_navigation_fallback_selected_state_follows_hash_target(tmp_path: Path):
    page = tmp_path / "index.html"
    page.write_text(_page(), encoding="utf-8")
    nav.patch_navigation(page)
    html = page.read_text(encoding="utf-8")
    assert 'genesis-target-aware-navigation' in html
    assert 'body:has(.view:target) .nav a.active{background:transparent;color:#9eb2c8;box-shadow:none}' in html
    assert 'body:has(#view-overview:target) .nav a[data-view="overview"]' in html
    assert 'body:has(#view-issues:target) .nav a[data-view="issues"]' in html
    assert 'body:has(#view-tasks:target) .nav a[data-view="tasks"]' in html


def test_navigation_fallback_is_idempotent(tmp_path: Path):
    page = tmp_path / "index.html"
    page.write_text(_page(), encoding="utf-8")
    nav.patch_navigation(page)
    first = page.read_text(encoding="utf-8")
    nav.patch_navigation(page)
    second = page.read_text(encoding="utf-8")
    assert first == second
    assert second.count('genesis-no-js-navigation') == 1
    assert second.count('genesis-target-aware-navigation') == 1


def test_navigation_fallback_rejects_missing_target(tmp_path: Path):
    page = tmp_path / "index.html"
    page.write_text('<html><head><style></style></head><body><nav class="nav"><button data-view="missing">Missing</button></nav></body></html>', encoding="utf-8")
    try:
        nav.patch_navigation(page)
    except RuntimeError as exc:
        assert "Broken dashboard navigation target" in str(exc)
    else:
        raise AssertionError("fallback must reject missing tab targets")


def test_pages_workflow_builds_hash_navigation_before_static_render():
    workflow = Path('.github/workflows/pages-status.yml').read_text(encoding='utf-8')
    assert 'python scripts/dashboard_navigation_fallback.py' in workflow
    assert workflow.index('python scripts/self_evaluation_dashboard.py') < workflow.index('python scripts/dashboard_navigation_fallback.py')
    assert workflow.index('python scripts/dashboard_navigation_fallback.py') < workflow.index('python scripts/render_static_dashboard.py')
