from pathlib import Path

from scripts import dashboard_continuous_improvement as review


def _write_dashboard(root: Path, html: str) -> None:
    path = root / "docs" / "status" / "index.html"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html, encoding="utf-8")


def _html(extra_style: str = "", extra_body: str = "") -> str:
    return f'''<!doctype html>
<html><head><meta name="viewport" content="width=device-width,initial-scale=1">
<style>.view{{display:none}} .view.active{{display:block}} {extra_style}</style></head>
<body>
<nav class="nav" aria-label="Dashboard"><button data-view="overview">Overview</button><button data-view="issues">Issues</button><button data-view="tasks">Tasks</button><button data-view="activity">Activity</button></nav>
<main id="main"><div id="updated">Loading</div><button>Refresh</button>
<section id="view-overview" class="view active"></section><section id="view-issues" class="view"></section><section id="view-tasks" class="view"></section><section id="view-activity" class="view"></section>{extra_body}</main>
</body></html>'''


def test_continuous_review_finds_multiple_grounded_improvements(tmp_path: Path):
    _write_dashboard(tmp_path, _html(extra_style="button{transition:opacity .2s}"))
    findings, views, _ = review.review_dashboard(tmp_path)
    keys = {finding.key for finding in findings}

    assert views == ["overview", "issues", "tasks", "activity"]
    assert "keyboard-focus-visibility" in keys
    assert "reduced-motion-support" in keys
    assert "skip-navigation-link" in keys
    assert "live-status-announcements" in keys
    assert "operator-search-filter" in keys


def test_improvements_disappear_when_evidence_is_present(tmp_path: Path):
    html = _html(
        extra_style="button:focus-visible{outline:2px solid} @media(prefers-reduced-motion:reduce){*{transition:none!important}}",
        extra_body='<a href="#main">Skip</a><div aria-live="polite"></div><input type="search" placeholder="Search items">',
    )
    _write_dashboard(tmp_path, html)
    findings, _, _ = review.review_dashboard(tmp_path)
    keys = {finding.key for finding in findings}

    assert "keyboard-focus-visibility" not in keys
    assert "reduced-motion-support" not in keys
    assert "skip-navigation-link" not in keys
    assert "live-status-announcements" not in keys
    assert "operator-search-filter" not in keys


def test_review_keeps_one_issue_selection_contract(tmp_path: Path):
    _write_dashboard(tmp_path, _html())
    findings, _, _ = review.review_dashboard(tmp_path)
    assert findings

    first = findings[0]
    marker = f"{review.base.MARKER_PREFIX}:{review.base.finding_fingerprint(first)}"
    selected = review.base.choose_finding(findings, [marker])
    assert selected is None or selected.key != first.key
