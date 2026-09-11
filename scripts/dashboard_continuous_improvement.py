from __future__ import annotations

import argparse
import os
import re
from pathlib import Path

from scripts import dashboard_hourly_review as base


DASHBOARD = Path("docs/status/index.html")


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""


def _runtime_text(files: list[Path]) -> str:
    return "\n".join(_read(path) for path in base.runtime_dashboard_files(files))


def continuous_findings(
    root: Path, views: list[str], files: list[Path]
) -> list[base.Finding]:
    """Derive bounded improvement opportunities from the dashboard as it exists now.

    Unlike the structural reviewer, these checks cover usability, accessibility,
    resilience, performance hygiene, and operator efficiency. Checks are based
    on concrete source evidence and adapt to the current dashboard/view set.
    """
    dashboard = root / DASHBOARD
    html = _read(dashboard)
    runtime = _runtime_text(files)
    combined = f"{html}\n{runtime}"
    lower = combined.lower()
    findings: list[base.Finding] = []

    interactive = bool(re.search(r"<(?:button|select|input|a)\b", html, flags=re.I))
    if interactive and "focus-visible" not in lower:
        findings.append(
            base.Finding(
                key="keyboard-focus-visibility",
                priority=76,
                title="Make keyboard focus clearly visible across dashboard controls",
                target="scripts/self_evaluation_dashboard.py",
                evidence=(
                    "The dashboard contains interactive controls but the runtime source has no "
                    ":focus-visible treatment, so keyboard users can lose their current position."
                ),
                acceptance=(
                    "Provide a clearly visible focus indicator for dashboard buttons, links, selects and inputs.",
                    "Keep the focus treatment readable in the existing dark theme and mobile layout.",
                    "Do not remove native focus behavior unless an equal or stronger replacement is present.",
                ),
                tabs=tuple(views),
            )
        )

    motion_present = any(token in lower for token in ("transition:", "animation:", "scroll-behavior"))
    if motion_present and "prefers-reduced-motion" not in lower:
        findings.append(
            base.Finding(
                key="reduced-motion-support",
                priority=70,
                title="Respect reduced-motion preferences in dashboard effects",
                target="scripts/self_evaluation_dashboard.py",
                evidence=(
                    "Runtime dashboard styling uses motion-capable effects but contains no "
                    "prefers-reduced-motion fallback."
                ),
                acceptance=(
                    "Add a prefers-reduced-motion rule that suppresses nonessential transitions and animations.",
                    "Preserve information, navigation and state changes when motion is reduced.",
                ),
                tabs=tuple(views),
            )
        )

    if "<main" in lower and not re.search(r'href=["\']#(?:main|content|dashboard)', html, flags=re.I):
        findings.append(
            base.Finding(
                key="skip-navigation-link",
                priority=66,
                title="Add a keyboard skip link to the dashboard main content",
                target="scripts/self_evaluation_dashboard.py",
                evidence=(
                    "The page has persistent sidebar navigation and a <main> region, but no source-level "
                    "skip link that lets keyboard users bypass repeated navigation."
                ),
                acceptance=(
                    "Add a keyboard-reachable skip link targeting the main dashboard content.",
                    "Keep the link unobtrusive until focused and ensure the target receives focus reliably.",
                ),
                tabs=tuple(views),
            )
        )

    live_status_tokens = ("loading", "updated", "waiting for data", "refresh")
    if any(token in lower for token in live_status_tokens) and "aria-live" not in lower:
        findings.append(
            base.Finding(
                key="live-status-announcements",
                priority=64,
                title="Announce dashboard refresh and loading state changes accessibly",
                target="scripts/self_evaluation_dashboard.py",
                evidence=(
                    "The dashboard exposes changing loading/updated status text but no aria-live region is "
                    "present for nonvisual users."
                ),
                acceptance=(
                    "Use a restrained live region for meaningful loading, refresh-success and refresh-failure status changes.",
                    "Avoid announcing rapidly changing decorative metrics or creating repetitive screen-reader noise.",
                ),
                tabs=tuple(views),
            )
        )

    has_fetch = "fetch(" in lower or "xmlhttprequest" in lower
    has_error_path = any(token in lower for token in (".catch(", "catch (", "catch(", "onerror", "error message"))
    if has_fetch and not has_error_path:
        findings.append(
            base.Finding(
                key="dashboard-fetch-failure-feedback",
                priority=78,
                title="Show a durable dashboard state when live data refresh fails",
                target="scripts/self_evaluation_dashboard.py",
                evidence=(
                    "Runtime dashboard code performs network fetches but no explicit fetch-error handling "
                    "was found in the reviewed runtime source."
                ),
                acceptance=(
                    "Handle live-data request failures without blanking already authenticated dashboard evidence.",
                    "Show a concise visible failure state and retain the last known-good snapshot when available.",
                    "Make retry behavior explicit and bounded.",
                ),
                tabs=tuple(views),
            )
        )

    operational_views = [view for view in views if view in {"issues", "tasks", "activity", "prs", "reports"}]
    has_filter_control = bool(
        re.search(r'<input\b[^>]*(?:type=["\']search["\']|placeholder=["\'][^"\']*(?:search|filter))', html, flags=re.I)
        or re.search(r'\b(?:search|filter)(?:Issues|Tasks|Activity|Prs|Reports|Items)?\s*\(', runtime)
    )
    if len(operational_views) >= 3 and not has_filter_control:
        findings.append(
            base.Finding(
                key="operator-search-filter",
                priority=60,
                title="Add a lightweight search or filter for operational dashboard lists",
                target="scripts/self_evaluation_dashboard.py",
                evidence=(
                    "The dashboard has multiple operational list views ("
                    + ", ".join(operational_views)
                    + ") but no discoverable search/filter control in the reviewed source."
                ),
                acceptance=(
                    "Provide a lightweight client-side way to narrow long operational lists without changing source data.",
                    "Keep the default view unchanged when no filter is active.",
                    "Make empty-filter results explicit and keyboard accessible.",
                ),
                tabs=tuple(operational_views),
            )
        )

    # A very large generated shell should not grow indefinitely without a size guard.
    try:
        dashboard_size = dashboard.stat().st_size
    except OSError:
        dashboard_size = 0
    tests_text = "\n".join(_read(path) for path in files if base._display_repo_path(path).startswith("tests/"))
    if dashboard_size > 300_000 and not re.search(r"(?:dashboard|index).*size|size.*(?:dashboard|index)|max.*bytes", tests_text, flags=re.I):
        findings.append(
            base.Finding(
                key="dashboard-size-budget",
                priority=56,
                title="Add a regression guard for generated dashboard size",
                target="scripts/validate_dashboard_artifact.py",
                evidence=(
                    f"The generated dashboard is {dashboard_size} bytes and no explicit dashboard-size regression "
                    "guard was found in dashboard/status tests."
                ),
                acceptance=(
                    "Add a documented generous size budget that catches accidental unbounded growth.",
                    "Keep the budget high enough that normal evidence growth does not create noisy failures.",
                ),
            )
        )

    findings.sort(key=lambda item: (-item.priority, item.key))
    return findings


def review_dashboard(root: Path = Path(".")) -> tuple[list[base.Finding], list[str], list[Path]]:
    structural, views, files = base.review_dashboard(root)
    expanded = structural + continuous_findings(root, views, files)
    # De-duplicate by stable key/target in case a future structural check overlaps.
    unique: dict[tuple[str, str], base.Finding] = {}
    for finding in expanded:
        unique.setdefault((finding.key, finding.target), finding)
    findings = sorted(unique.values(), key=lambda item: (-item.priority, item.key))
    return findings, views, files


def create_issue(repo: str, token: str, finding: base.Finding, views: list[str], files: list[Path]) -> str:
    response = base._post_json(
        f"https://api.github.com/repos/{repo}/issues",
        {
            "title": f"[Genesis Task] Dashboard improvement — {finding.title}",
            "body": base.issue_body(finding, views, files),
            "labels": ["genesis-task", base.LABEL, "genesis-autonomous"],
        },
        token,
    )
    if not isinstance(response, dict):
        raise RuntimeError("GitHub returned an invalid issue response")
    return str(response.get("html_url") or response.get("url") or "")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Continuously review the Genesis dashboard and create at most one grounded improvement Issue."
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    findings, views, files = review_dashboard()
    print(f"Reviewed {len(views)} dashboard tabs and {len(files)} dashboard files.")
    print(f"Grounded dashboard findings available: {len(findings)}")
    if not findings:
        print("No grounded dashboard improvement found.")
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

    chosen = base.choose_finding(findings, base.open_issue_texts(repo, token))
    if chosen is None:
        print("All current dashboard findings already have equivalent open Issues.")
        return 0

    url = create_issue(repo, token, chosen, views, files)
    print(f"Created dashboard improvement Issue: {url}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
