from __future__ import annotations

import re
from pathlib import Path

DASHBOARD = Path("docs/status/index.html")

REQUIRED_IDS = (
    "heroTitle",
    "ai",
    "coverage",
    "autonomy",
    "focus",
    "gapList",
    "targets",
    "taskStats",
    "peerGrid",
    "activity",
    "prs",
    "report",
    "buildMeta",
)


def _inner(html: str, element_id: str) -> str:
    match = re.search(
        rf'<(?P<tag>[A-Za-z0-9]+)\b[^>]*\bid="{re.escape(element_id)}"[^>]*>(.*?)</(?P=tag)>',
        html,
        flags=re.S,
    )
    if not match:
        raise RuntimeError(f"Generated dashboard is missing #{element_id}")
    return re.sub(r"<[^>]+>", "", match.group(2)).strip()


def validate(path: Path = DASHBOARD) -> None:
    if not path.is_file():
        raise RuntimeError(f"Dashboard not found: {path}")
    html = path.read_text(encoding="utf-8")

    if "Loading Genesis" in _inner(html, "heroTitle"):
        raise RuntimeError("Generated dashboard still publishes a loading placeholder")
    if _inner(html, "ai") in {"", "—", "-"}:
        raise RuntimeError("Generated dashboard has no static AI capability value")
    if "Build pending" in _inner(html, "buildMeta"):
        raise RuntimeError("Generated dashboard has no deployed build identity")

    for element_id in REQUIRED_IDS:
        if not _inner(html, element_id):
            raise RuntimeError(f"Generated dashboard section #{element_id} has no static content")

    links = re.findall(r'<a[^>]*data-view="([^"]+)"[^>]*href="#view-([^"]+)"', html)
    if len(links) < 8:
        raise RuntimeError("Generated dashboard does not expose the expected tab navigation")
    for view, target in links:
        if view != target or f'id="view-{target}"' not in html:
            raise RuntimeError(f"Generated dashboard contains a broken tab target: {view} -> {target}")

    if "genesis-no-js-navigation" not in html:
        raise RuntimeError("Generated dashboard lost no-JavaScript navigation fallback")
    if "genesis-dashboard-v3" not in html:
        raise RuntimeError("Generated dashboard lost the v3 reliability shell")


if __name__ == "__main__":
    validate()
