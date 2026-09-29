from __future__ import annotations

import re
from collections import Counter
from html.parser import HTMLParser
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


class _DashboardNavigationParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.targets: list[str] = []
        self.controls: list[tuple[str, str, str | None]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        element_id = attributes.get("id") or ""
        if tag == "section" and element_id.startswith("view-"):
            self.targets.append(element_id.removeprefix("view-"))

        view = attributes.get("data-view")
        if tag in {"a", "button"} and view is not None:
            self.controls.append((tag, view, attributes.get("href")))


def _validate_navigation(html: str) -> None:
    parser = _DashboardNavigationParser()
    parser.feed(html)

    if not parser.targets:
        raise RuntimeError("Generated dashboard does not expose any tab targets")
    if not parser.controls:
        raise RuntimeError("Generated dashboard does not expose any tab controls")

    duplicate_targets = sorted(name for name, count in Counter(parser.targets).items() if count > 1)
    if duplicate_targets:
        raise RuntimeError("Generated dashboard has duplicate tab targets: " + ", ".join(duplicate_targets))

    control_names = [view for _tag, view, _href in parser.controls]
    duplicate_controls = sorted(name for name, count in Counter(control_names).items() if count > 1)
    if duplicate_controls:
        raise RuntimeError("Generated dashboard has duplicate tab controls: " + ", ".join(duplicate_controls))

    for tag, view, href in parser.controls:
        expected_href = f"#view-{view}"
        if tag != "a" or href != expected_href:
            raise RuntimeError(
                f"Generated dashboard contains a broken tab control: "
                f"{tag} data-view={view!r} href={href!r}; expected an anchor to {expected_href!r}"
            )

    targets = set(parser.targets)
    controls = set(control_names)
    missing_controls = sorted(targets - controls)
    if missing_controls:
        raise RuntimeError(
            "Generated dashboard has tab targets without navigable controls: " + ", ".join(missing_controls)
        )
    orphan_controls = sorted(controls - targets)
    if orphan_controls:
        raise RuntimeError(
            "Generated dashboard has tab controls without matching targets: " + ", ".join(orphan_controls)
        )


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

    _validate_navigation(html)
    if "genesis-no-js-navigation" not in html:
        raise RuntimeError("Generated dashboard lost no-JavaScript navigation fallback")
    if "genesis-dashboard-v3" not in html:
        raise RuntimeError("Generated dashboard lost the v3 reliability shell")


if __name__ == "__main__":
    validate()
