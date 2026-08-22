from __future__ import annotations

from pathlib import Path

DASHBOARD = Path("docs/status/index.html")

CSS = r'''
/* genesis-dashboard-v3 */
.buildmeta{font-size:8px;color:var(--muted);margin-top:4px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:360px}
.nav{overscroll-behavior:contain}.nav [data-view]{transition:background .15s ease,color .15s ease}
@media(max-width:720px){
  .side{position:sticky;top:0;z-index:40;padding:10px 10px 8px;border-right:0;border-bottom:1px solid var(--line);background:#071521f5;backdrop-filter:blur(12px)}
  .brand{padding:0 4px 8px}.brand .logo{width:28px;height:28px}.selector{display:none}
  .nav{display:flex!important;gap:6px;margin-top:0;overflow-x:auto;padding:2px 1px 4px;scrollbar-width:none}.nav::-webkit-scrollbar{display:none}
  .nav [data-view]{flex:0 0 auto;min-height:38px!important;height:38px!important;padding:0 12px!important;border:1px solid #1c3850!important;background:#0b1d2e!important;border-radius:999px!important;box-shadow:none!important;white-space:nowrap}
  .nav [data-view].active{border-color:#4c899d!important;background:#15304a!important}
  .top{padding:12px 13px;align-items:flex-start}.title h1{font-size:17px}.updated{max-width:42vw;text-align:right;line-height:1.4}.buildmeta{max-width:42vw}
  .content{padding-top:12px}.hero{padding:17px}.heroNum{font-size:36px}.card{padding:14px}
}
'''


def patch(path: Path = DASHBOARD) -> None:
    if not path.is_file():
        raise RuntimeError(f"Dashboard not found: {path}")
    html = path.read_text(encoding="utf-8")
    if "genesis-dashboard-v3" not in html:
        if "</style>" not in html:
            raise RuntimeError("Dashboard style marker not found")
        html = html.replace("</style>", CSS + "\n</style>", 1)

    if 'id="buildMeta"' not in html:
        marker = '<div id="updated" class="updated">'
        pos = html.find(marker)
        if pos < 0:
            raise RuntimeError("Dashboard updated marker not found")
        end = html.find("</div>", pos)
        if end < 0:
            raise RuntimeError("Dashboard updated element is malformed")
        end += len("</div>")
        html = html[:end] + '<div id="buildMeta" class="buildmeta">Build pending</div>' + html[end:]

    html = html.replace("Command Center · Evidence v2", "Command Center · Evidence v3")
    path.write_text(html, encoding="utf-8")


if __name__ == "__main__":
    patch()
