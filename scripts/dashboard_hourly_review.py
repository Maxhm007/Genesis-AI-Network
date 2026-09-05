from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

DASHBOARD = Path("docs/status/index.html")
LABEL = "genesis-dashboard-review"
MARKER_PREFIX = "genesis-dashboard-review"
MAX_MANIFEST_FILES = 80


@dataclass(frozen=True)
class Finding:
    key: str
    priority: int
    title: str
    target: str
    evidence: str
    acceptance: tuple[str, ...]
    tabs: tuple[str, ...] = ()


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""


def dashboard_files(root: Path = Path(".")) -> list[Path]:
    """Discover the complete dashboard implementation surface.

    The scope is intentionally broader than files whose names contain
    "dashboard": status artifacts, renderers, validators, tests, workflows,
    and any source file that explicitly references docs/status are included.
    """
    candidates: set[Path] = set()

    status_dir = root / "docs" / "status"
    if status_dir.is_dir():
        candidates.update(path for path in status_dir.rglob("*") if path.is_file())

    globs = (
        "scripts/*dashboard*.py",
        "scripts/*status*.py",
        "scripts/render_static*.py",
        "scripts/build_gene_chat.py",
        "tests/test_dashboard*.py",
        "tests/test_*status*.py",
        ".github/workflows/*dashboard*.yml",
        ".github/workflows/*dashboard*.yaml",
        ".github/workflows/*status*.yml",
        ".github/workflows/*status*.yaml",
    )
    for pattern in globs:
        candidates.update(path for path in root.glob(pattern) if path.is_file())

    for base in (root / "scripts", root / "tests", root / ".github" / "workflows"):
        if not base.is_dir():
            continue
        for path in base.iterdir():
            if not path.is_file() or path.suffix.lower() not in {".py", ".yml", ".yaml"}:
                continue
            text = _read(path)
            if "docs/status" in text or "docs/status/index.html" in text:
                candidates.add(path)

    return sorted(candidates, key=lambda path: path.as_posix())


def discover_views(html: str) -> list[str]:
    views = re.findall(r'<(?:a|button)\b[^>]*\bdata-view="([^"]+)"', html, flags=re.I)
    return list(dict.fromkeys(view.strip() for view in views if view.strip()))


def _ids(html: str) -> list[str]:
    return re.findall(r'\bid="([^"]+)"', html, flags=re.I)


def _combined_text(files: Iterable[Path]) -> str:
    return "\n".join(_read(path) for path in files)


def _display_repo_path(path: Path) -> str:
    value = path.as_posix()
    for marker in ("/docs/", "/scripts/", "/tests/", "/.github/"):
        if marker in value:
            return value[value.index(marker) + 1 :]
    if value.startswith("./"):
        return value[2:]
    return value


def runtime_dashboard_files(files: Iterable[Path]) -> list[Path]:
    """Return implementation sources that can prove runtime dashboard behavior.

    Tests, the hourly reviewer itself, and workflow text remain part of the full
    audit manifest, but cannot satisfy runtime feature checks merely by naming
    the behavior that the reviewer is searching for.
    """
    runtime: list[Path] = []
    for path in files:
        display = _display_repo_path(path)
        if display == "scripts/dashboard_hourly_review.py":
            continue
        if display.startswith("tests/") or display.startswith(".github/workflows/"):
            continue
        runtime.append(path)
    return runtime


def review_dashboard(root: Path = Path(".")) -> tuple[list[Finding], list[str], list[Path]]:
    dashboard = root / DASHBOARD
    files = dashboard_files(root)
    if not dashboard.is_file():
        return (
            [
                Finding(
                    key="dashboard-root-missing",
                    priority=100,
                    title="Restore the generated dashboard root",
                    target="scripts/self_evaluation_dashboard.py",
                    evidence=f"{DASHBOARD.as_posix()} is missing, so no dashboard tab can be reviewed.",
                    acceptance=(
                        "Generate docs/status/index.html from the authoritative dashboard builder.",
                        "Keep the generated dashboard compatible with the existing render and validation chain.",
                    ),
                )
            ],
            [],
            files,
        )

    html = _read(dashboard)
    views = discover_views(html)
    combined = _combined_text(runtime_dashboard_files(files))
    findings: list[Finding] = []

    if not views:
        findings.append(
            Finding(
                key="dashboard-navigation-missing",
                priority=100,
                title="Restore dashboard navigation discovery",
                target="scripts/self_evaluation_dashboard.py",
                evidence="The rendered dashboard has no data-view navigation controls.",
                acceptance=(
                    "Render at least one navigation control with a deterministic data-view.",
                    "Ensure each navigation control maps to one existing view section.",
                ),
            )
        )
        return findings, views, files

    missing_targets = [view for view in views if f'id="view-{view}"' not in html]
    if missing_targets:
        findings.append(
            Finding(
                key="missing-tab-targets:" + ",".join(missing_targets),
                priority=100,
                title="Repair dashboard tabs with missing view targets",
                target="scripts/self_evaluation_dashboard.py",
                evidence="Navigation target section missing for: " + ", ".join(missing_targets),
                acceptance=tuple(
                    f'Ensure data-view="{view}" maps to id="view-{view}".' for view in missing_targets
                ),
                tabs=tuple(missing_targets),
            )
        )

    ids = _ids(html)
    duplicate_ids = sorted({item for item in ids if ids.count(item) > 1})
    if duplicate_ids:
        findings.append(
            Finding(
                key="duplicate-dashboard-ids:" + ",".join(duplicate_ids[:12]),
                priority=96,
                title="Remove duplicate dashboard DOM identifiers",
                target="scripts/self_evaluation_dashboard.py",
                evidence="Duplicate DOM ids can make tab rendering update the wrong element: "
                + ", ".join(duplicate_ids[:12]),
                acceptance=(
                    "Every rendered DOM id is unique.",
                    "Existing tab selectors and render bindings continue to resolve exactly one element.",
                ),
            )
        )

    title_missing = [
        view
        for view in views
        if not re.search(rf'(?:^|[{{,])\s*{re.escape(view)}\s*:\s*\[', html)
    ]
    if title_missing and "function switchView" in html:
        findings.append(
            Finding(
                key="tab-header-map-incomplete:" + ",".join(title_missing),
                priority=92,
                title="Keep dashboard header metadata synchronized with every tab",
                target="scripts/self_evaluation_dashboard.py",
                evidence="switchView header metadata is missing for: " + ", ".join(title_missing),
                acceptance=tuple(
                    f"Switching to {view} updates the page title/subtitle without a JavaScript error."
                    for view in title_missing
                ),
                tabs=tuple(title_missing),
            )
        )

    if "genesis-no-js-navigation" not in combined:
        findings.append(
            Finding(
                key="no-navigation-fallback-source",
                priority=90,
                title="Add a no-JavaScript fallback for every dashboard tab",
                target="scripts/dashboard_navigation_fallback.py",
                evidence="No runtime dashboard source contains the genesis-no-js-navigation reliability marker.",
                acceptance=(
                    "All current data-view controls remain navigable if enhancement JavaScript fails.",
                    "Fallback navigation is generated from the current tab list instead of a hard-coded subset.",
                ),
                tabs=tuple(views),
            )
        )

    if "hashchange" not in combined:
        findings.append(
            Finding(
                key="hash-history-not-synchronized",
                priority=72,
                title="Synchronize dashboard tab state with deep links and browser history",
                target="scripts/dashboard_navigation_fallback.py",
                evidence=(
                    "The runtime dashboard implementation contains no hashchange handling. "
                    "Deep links/back-forward navigation can change :target without synchronizing "
                    "the enhanced header/selected-state logic."
                ),
                acceptance=(
                    "Opening a #view-* deep link initializes the matching tab state.",
                    "Browser Back/Forward keeps visible view, selected navigation item, page title and subtitle synchronized.",
                    "Unknown hashes fail safely without hiding the default Overview view.",
                ),
                tabs=tuple(views),
            )
        )

    if "aria-current" not in combined:
        findings.append(
            Finding(
                key="active-tab-not-exposed-accessibly",
                priority=68,
                title="Expose the active dashboard tab to assistive technology",
                target="scripts/dashboard_navigation_fallback.py",
                evidence=(
                    "No runtime dashboard source uses aria-current, so the visually selected tab is not "
                    "programmatically exposed as the current navigation item."
                ),
                acceptance=(
                    'The active dashboard navigation item uses aria-current="page" (or an equivalent correct semantic).',
                    "Inactive navigation items do not retain a stale current-state attribute.",
                    "Hash fallback and JavaScript-enhanced navigation keep the accessibility state synchronized.",
                ),
                tabs=tuple(views),
            )
        )

    nav_tag = re.search(r'<nav\b[^>]*class="[^"]*\bnav\b[^"]*"[^>]*>', html, flags=re.I)
    if nav_tag and not re.search(r'\baria-label=', nav_tag.group(0), flags=re.I):
        findings.append(
            Finding(
                key="dashboard-nav-landmark-unlabelled",
                priority=64,
                title="Label the dashboard navigation landmark",
                target="scripts/self_evaluation_dashboard.py",
                evidence='The primary <nav class="nav"> landmark has no aria-label.',
                acceptance=(
                    "Give the dashboard tab navigation a concise accessible label.",
                    "Preserve existing visual layout and mobile behavior.",
                ),
                tabs=tuple(views),
            )
        )

    tests_text = "\n".join(
        _read(path) for path in files if _display_repo_path(path).startswith("tests/")
    )
    unmentioned_views = [view for view in views if view not in tests_text]
    if unmentioned_views:
        findings.append(
            Finding(
                key="tab-regression-coverage:" + ",".join(unmentioned_views),
                priority=58,
                title="Extend regression coverage across every dashboard tab",
                target="scripts/validate_dashboard_artifact.py",
                evidence="Dashboard tabs not referenced by dashboard/status regression tests: "
                + ", ".join(unmentioned_views),
                acceptance=(
                    "Validation derives the current tab list from the generated dashboard.",
                    "Every current tab is checked for a matching target and navigable control.",
                    "Future tabs enter the same validation automatically without a manual allowlist.",
                ),
                tabs=tuple(unmentioned_views),
            )
        )

    findings.sort(key=lambda item: (-item.priority, item.key))
    return findings, views, files


def _request_json(url: str, token: str) -> object:
    request = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "User-Agent": "Genesis-AI-Network/dashboard-hourly-review",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def _post_json(url: str, payload: dict, token: str) -> object:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
            "User-Agent": "Genesis-AI-Network/dashboard-hourly-review",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def open_issue_texts(repo: str, token: str) -> list[str]:
    texts: list[str] = []
    for page in range(1, 6):
        query = urllib.parse.urlencode(
            {"state": "open", "per_page": 100, "page": page, "sort": "created", "direction": "desc"}
        )
        rows = _request_json(f"https://api.github.com/repos/{repo}/issues?{query}", token)
        if not isinstance(rows, list):
            break
        for row in rows:
            if isinstance(row, dict) and "pull_request" not in row:
                texts.append(f"{row.get('title') or ''}\n{row.get('body') or ''}")
        if len(rows) < 100:
            break
    return texts


def finding_fingerprint(finding: Finding) -> str:
    canonical = f"{finding.key}|{finding.target}".encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()[:16]


def choose_finding(findings: Iterable[Finding], existing_open_issue_texts: Iterable[str]) -> Finding | None:
    existing = "\n".join(existing_open_issue_texts).lower()
    for finding in findings:
        marker = f"{MARKER_PREFIX}:{finding_fingerprint(finding)}"
        if marker.lower() not in existing:
            return finding
    return None


def issue_body(finding: Finding, views: list[str], files: list[Path]) -> str:
    fingerprint = finding_fingerprint(finding)
    reviewed_tabs = ", ".join(views) if views else "none discovered"
    manifest = [_display_repo_path(path) for path in files[:MAX_MANIFEST_FILES]]
    manifest_text = "\n".join(f"- `{path}`" for path in manifest) or "- none"
    if len(files) > MAX_MANIFEST_FILES:
        manifest_text += f"\n- ... plus {len(files) - MAX_MANIFEST_FILES} additional discovered dashboard files"

    acceptance = "\n".join(f"- {item}" for item in finding.acceptance)
    affected = ", ".join(finding.tabs) if finding.tabs else "whole dashboard"
    return f"""<!-- {MARKER_PREFIX}:{fingerprint} -->
This GitHub Issue is the authoritative task record for one improvement selected by the hourly whole-dashboard Genesis review.

Genesis-Problem-Fingerprint: dashboard-review:{fingerprint}
- **Task type:** `dashboard_improvement`
- **Source:** `genesis.dashboard.hourly_review`
- **Priority:** {finding.priority}
- **Target:** `{finding.target}`

### Finding
{finding.evidence}

Affected tabs: {affected}

### Objective
{finding.title}. Implement the smallest durable source-level improvement so regenerated/published dashboard output keeps the fix.

### Acceptance
{acceptance}
- Re-run dashboard validation/regression tests.
- Preserve security boundaries, owner controls, existing Issue Solver routing, and unrelated dashboard behavior.

### Hourly review evidence
Reviewed tabs ({len(views)}): {reviewed_tabs}

Reviewed dashboard files ({len(files)}):
{manifest_text}

### Review rule
The hourly dashboard review creates at most one new actionable Issue per run. An equivalent open Issue suppresses duplicates; once resolved, a genuinely recurring regression may be reported again.
"""


def create_issue(repo: str, token: str, finding: Finding, views: list[str], files: list[Path]) -> str:
    response = _post_json(
        f"https://api.github.com/repos/{repo}/issues",
        {
            "title": f"[Genesis Task] Dashboard improvement — {finding.title}",
            "body": issue_body(finding, views, files),
            "labels": ["genesis-task", LABEL],
        },
        token,
    )
    if not isinstance(response, dict):
        raise RuntimeError("GitHub returned an invalid issue response")
    return str(response.get("html_url") or response.get("url") or "")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Review the whole Genesis dashboard and create at most one improvement Issue."
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    findings, views, files = review_dashboard()
    print(f"Reviewed {len(views)} dashboard tabs and {len(files)} dashboard files.")
    if not findings:
        print("No actionable dashboard improvement found.")
        return 0

    repo = str(os.environ.get("GITHUB_REPOSITORY") or "").strip()
    token = str(os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN") or "").strip()
    if args.dry_run:
        chosen = findings[0]
        print(f"Dry-run finding: {chosen.title} -> {chosen.target}")
        return 0
    if not repo or not token:
        print("GitHub repository/token unavailable; review completed without creating an Issue.")
        return 0

    chosen = choose_finding(findings, open_issue_texts(repo, token))
    if chosen is None:
        print("All current dashboard findings already have equivalent open Issues.")
        return 0

    url = create_issue(repo, token, chosen, views, files)
    print(f"Created dashboard improvement Issue: {url}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
