from pathlib import Path

from scripts import dashboard_hourly_review as review


def _write(root: Path, relative: str, content: str) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _dashboard() -> str:
    return """<!doctype html><html><body>
<nav class="nav"><a class="active" data-view="overview" href="#view-overview">Overview</a><a data-view="issues" href="#view-issues">Issues</a><a data-view="tasks" href="#view-tasks">Tasks</a></nav>
<section class="view active" id="view-overview"></section><section class="view" id="view-issues"></section><section class="view" id="view-tasks"></section>
<script>function switchView(v){const names={overview:['Overview','o'],issues:['Issues','i'],tasks:['Tasks','t']};return names[v]}</script>
</body></html>"""


def test_dashboard_files_cover_rendered_generators_validators_tests_and_workflows(tmp_path: Path):
    _write(tmp_path, "docs/status/index.html", _dashboard())
    _write(tmp_path, "docs/status/status.json", "{}")
    _write(tmp_path, "scripts/dashboard_patch.py", "DASHBOARD='docs/status/index.html'")
    _write(tmp_path, "scripts/render_static_sections.py", "DASHBOARD='docs/status/index.html'")
    _write(tmp_path, "scripts/unrelated.py", "print('no dashboard')")
    _write(tmp_path, "tests/test_dashboard_contract.py", "assert True")
    _write(tmp_path, ".github/workflows/status-publish.yml", "run: echo docs/status/index.html")

    paths = {path.relative_to(tmp_path).as_posix() for path in review.dashboard_files(tmp_path)}
    assert "docs/status/index.html" in paths
    assert "docs/status/status.json" in paths
    assert "scripts/dashboard_patch.py" in paths
    assert "scripts/render_static_sections.py" in paths
    assert "tests/test_dashboard_contract.py" in paths
    assert ".github/workflows/status-publish.yml" in paths
    assert "scripts/unrelated.py" not in paths


def test_discover_views_is_dynamic_and_keeps_order():
    assert review.discover_views(_dashboard()) == ["overview", "issues", "tasks"]


def test_review_reports_missing_target_before_optional_improvements(tmp_path: Path):
    broken = _dashboard().replace('<section class="view" id="view-tasks"></section>', "")
    _write(tmp_path, "docs/status/index.html", broken)
    findings, views, files = review.review_dashboard(tmp_path)
    assert views == ["overview", "issues", "tasks"]
    assert files
    assert findings[0].key.startswith("missing-tab-targets:")
    assert findings[0].target == "scripts/self_evaluation_dashboard.py"
    assert "tasks" in findings[0].tabs


def test_review_uses_whole_chain_to_detect_existing_reliability_features(tmp_path: Path):
    _write(tmp_path, "docs/status/index.html", _dashboard())
    _write(
        tmp_path,
        "scripts/dashboard_navigation_fallback.py",
        "# genesis-no-js-navigation\n# hashchange\n# aria-current\n",
    )
    _write(tmp_path, "tests/test_dashboard_all_tabs.py", "overview issues tasks")
    findings, _, _ = review.review_dashboard(tmp_path)
    keys = {finding.key for finding in findings}
    assert "no-navigation-fallback-source" not in keys
    assert "hash-history-not-synchronized" not in keys
    assert "active-tab-not-exposed-accessibly" not in keys
    assert not any(key.startswith("tab-regression-coverage:") for key in keys)
    assert "dashboard-nav-landmark-unlabelled" in keys


def test_choose_finding_creates_at_most_one_and_suppresses_equivalent_open_issue():
    findings = [
        review.Finding("a", 100, "First", "scripts/a.py", "evidence", ("done",)),
        review.Finding("b", 90, "Second", "scripts/b.py", "evidence", ("done",)),
    ]
    first = review.choose_finding(findings, [])
    assert first == findings[0]
    marker = f"<!-- {review.MARKER_PREFIX}:{review.finding_fingerprint(findings[0])} -->"
    second = review.choose_finding(findings, [marker])
    assert second == findings[1]


def test_issue_body_records_tabs_full_scope_target_and_acceptance(tmp_path: Path):
    _write(tmp_path, "docs/status/index.html", _dashboard())
    _write(tmp_path, "scripts/dashboard_patch.py", "DASHBOARD='docs/status/index.html'")
    files = review.dashboard_files(tmp_path)
    finding = review.Finding(
        "history",
        72,
        "Synchronize history",
        "scripts/dashboard_navigation_fallback.py",
        "No hashchange handler.",
        ("Back works.", "Forward works."),
        ("overview", "issues", "tasks"),
    )
    body = review.issue_body(finding, ["overview", "issues", "tasks"], files)
    assert '- **Target:** `scripts/dashboard_navigation_fallback.py`' in body
    assert "Reviewed tabs (3): overview, issues, tasks" in body
    assert "`docs/status/index.html`" in body
    assert "`scripts/dashboard_patch.py`" in body
    assert "Back works." in body
    assert review.MARKER_PREFIX in body


def test_runtime_feature_checks_ignore_reviewer_tests_and_workflow_vocabulary(tmp_path: Path):
    _write(tmp_path, "docs/status/index.html", _dashboard())
    _write(tmp_path, "scripts/dashboard_navigation_fallback.py", "# genesis-no-js-navigation\n")
    _write(tmp_path, "scripts/dashboard_hourly_review.py", "# hashchange aria-current\n")
    _write(tmp_path, "tests/test_dashboard_words.py", "# hashchange aria-current overview issues tasks\n")
    _write(tmp_path, ".github/workflows/dashboard-review.yml", "# hashchange aria-current\n")
    findings, _, files = review.review_dashboard(tmp_path)
    keys = {finding.key for finding in findings}
    assert "hash-history-not-synchronized" in keys
    assert "active-tab-not-exposed-accessibly" in keys
    assert any(review._display_repo_path(path) == "scripts/dashboard_hourly_review.py" for path in files)


def test_display_repo_path_preserves_dot_github():
    assert review._display_repo_path(Path(".github/workflows/dashboard.yml")) == ".github/workflows/dashboard.yml"


def test_current_repository_dashboard_has_tabs_and_each_target_exists():
    html = Path("docs/status/index.html").read_text(encoding="utf-8")
    views = review.discover_views(html)
    assert views
    for view in views:
        assert f'id="view-{view}"' in html


def test_hourly_workflow_contract():
    workflow = Path(".github/workflows/genesis-hourly-dashboard-review.yml").read_text(encoding="utf-8")
    assert "cron: '17 * * * *'" in workflow
    assert "workflow_dispatch:" in workflow
    assert "contents: read" in workflow
    assert "issues: write" in workflow
    assert "contents: write" not in workflow
    assert "python -m pytest -q tests/test_dashboard_hourly_review.py" in workflow
    assert "python scripts/dashboard_hourly_review.py" in workflow
