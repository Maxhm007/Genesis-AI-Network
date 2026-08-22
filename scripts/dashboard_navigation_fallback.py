from __future__ import annotations

import re
from pathlib import Path

DASHBOARD = Path("docs/status/index.html")

FALLBACK_CSS = r'''
/* genesis-no-js-navigation */
.nav a{border:0;background:transparent;color:#9eb2c8;height:37px;border-radius:9px;text-align:left;padding:0 11px;cursor:pointer;font-size:11px;font-weight:680;display:flex;align-items:center;text-decoration:none}
.nav a:hover{background:#ffffff08;color:#fff}.nav a.active{background:#15304a;color:#fff;box-shadow:inset 3px 0 0 var(--cyan)}
.view{scroll-margin-top:12px}.view:target{display:block}
body:has(.view:target) .view.active:not(:target){display:none}
@media(max-width:720px){.nav a{min-height:48px;height:auto}}
'''


def patch_navigation(path: Path = DASHBOARD) -> None:
    if not path.is_file():
        raise RuntimeError(f"Dashboard not found: {path}")
    html = path.read_text(encoding="utf-8")

    # Convert every generated dashboard nav control into a normal hash link.
    # This keeps tab navigation functional even if the enhancement JavaScript
    # fails to execute in the browser.
    pattern = re.compile(r'<button(?P<attrs>[^>]*)\bdata-view="(?P<view>[^"]+)"(?P<tail>[^>]*)>(?P<label>.*?)</button>', re.S)

    def repl(match: re.Match[str]) -> str:
        attrs = (match.group("attrs") + match.group("tail")).strip()
        attrs = re.sub(r'\s*onclick="[^"]*"', '', attrs)
        return f'<a {attrs} data-view="{match.group("view")}" href="#view-{match.group("view")}">{match.group("label")}</a>'

    html, count = pattern.subn(repl, html)
    if count < 1 and 'genesis-no-js-navigation' not in html:
        raise RuntimeError("No dashboard navigation controls found for fallback conversion")

    if "genesis-no-js-navigation" not in html:
        if "</style>" not in html:
            raise RuntimeError("Dashboard style marker not found")
        html = html.replace("</style>", FALLBACK_CSS + "\n</style>", 1)

    # Progressive enhancement must bind to either anchors or legacy buttons.
    html = html.replace("document.querySelectorAll('.nav button')", "document.querySelectorAll('.nav [data-view]')")

    # Verify every nav target exists in the generated page.
    links = re.findall(r'<a[^>]*data-view="([^"]+)"[^>]*href="#view-([^"]+)"', html)
    if not links:
        raise RuntimeError("No hash navigation links generated")
    for view, target in links:
        if view != target or f'id="view-{target}"' not in html:
            raise RuntimeError(f"Broken dashboard navigation target: {view} -> {target}")

    path.write_text(html, encoding="utf-8")


if __name__ == "__main__":
    patch_navigation()
