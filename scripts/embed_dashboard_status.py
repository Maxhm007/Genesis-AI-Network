from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

STATUS = Path("docs/status/status.json")
DASHBOARD = Path("docs/status/index.html")
MARKER_ID = "genesisEmbeddedStatus"


def _script(payload: dict[str, Any]) -> str:
    # JSON is generated locally from the authenticated Pages build. Escape the
    # closing-script sequence defensively so payload text can never terminate
    # the inline script early.
    raw = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).replace("</", "<\\/")
    return f'''<script id="{MARKER_ID}">
window.__GENESIS_STATUS__={raw};
(function(){{
  const boot=window.__GENESIS_STATUS__;
  try{{
    if(typeof DATA!=="undefined")DATA=boot;
    const updated=document.querySelector("#updated");
    const side=document.querySelector("#sideUpdated");
    const txt=(typeof age==="function")?`Snapshot ${{age(boot.generated_at)}} · embedded evidence`:'Embedded authenticated snapshot';
    if(updated)updated.textContent=txt;
    if(side)side.textContent=txt;
    if(typeof render==="function")render();
  }}catch(e){{
    const updated=document.querySelector("#updated");
    if(updated)updated.textContent='Embedded snapshot render error: '+(e&&e.message?e.message:'unknown');
  }}
}})();
</script>'''


def embed(status_path: Path = STATUS, dashboard_path: Path = DASHBOARD) -> None:
    if not status_path.is_file():
        raise RuntimeError(f"Status snapshot not found: {status_path}")
    if not dashboard_path.is_file():
        raise RuntimeError(f"Dashboard not found: {dashboard_path}")

    payload = json.loads(status_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or "generated_at" not in payload:
        raise RuntimeError("Status snapshot is not a valid generated dashboard payload")

    html = dashboard_path.read_text(encoding="utf-8")
    block = _script(payload)
    existing = re.compile(rf'<script id="{re.escape(MARKER_ID)}">.*?</script>', re.S)
    if existing.search(html):
        html = existing.sub(block, html, count=1)
    else:
        marker = "</body>"
        if marker not in html:
            raise RuntimeError("Dashboard body marker not found; refusing blind embedded-status injection")
        html = html.replace(marker, block + "\n" + marker, 1)
    dashboard_path.write_text(html, encoding="utf-8")


if __name__ == "__main__":
    embed()
