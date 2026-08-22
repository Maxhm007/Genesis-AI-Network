from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

STATUS = Path("docs/status/status.json")
DASHBOARD = Path("docs/status/index.html")
MARKER_ID = "genesisEmbeddedStatus"
RUNTIME_MARKER = "<script>\nlet DATA=null"
BOOT_MARKER = "refreshMinute();setInterval(refreshMinute,60000);"
EMBEDDED_BOOT_MARKER = "/* genesis-embedded-first-paint */"


def _payload_script(payload: dict[str, Any]) -> str:
    """Return a data-only script that is safe to execute before dashboard runtime."""
    raw = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).replace("</", "<\\/")
    return f'<script id="{MARKER_ID}">window.__GENESIS_STATUS__={raw};</script>'


def _boot_hook() -> str:
    """Render embedded evidence from inside the initialized dashboard runtime."""
    return (
        EMBEDDED_BOOT_MARKER
        + "if(window.__GENESIS_STATUS__){"
        + "DATA=window.__GENESIS_STATUS__;"
        + "const embeddedTxt=`Snapshot ${age(DATA.generated_at)} · embedded evidence`;"
        + "$('#updated').textContent=embeddedTxt;"
        + "$('#sideUpdated').textContent=embeddedTxt;"
        + "render();"
        + "}"
    )


def embed(status_path: Path = STATUS, dashboard_path: Path = DASHBOARD) -> None:
    if not status_path.is_file():
        raise RuntimeError(f"Status snapshot not found: {status_path}")
    if not dashboard_path.is_file():
        raise RuntimeError(f"Dashboard not found: {dashboard_path}")

    payload = json.loads(status_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or "generated_at" not in payload:
        raise RuntimeError("Status snapshot is not a valid generated dashboard payload")

    html = dashboard_path.read_text(encoding="utf-8")
    block = _payload_script(payload)

    # Remove any older embedded block first. The payload must be declared before
    # the dashboard runtime so the runtime can deterministically consume it.
    existing = re.compile(rf'<script id="{re.escape(MARKER_ID)}">.*?</script>\s*', re.S)
    html = existing.sub("", html, count=1)

    if RUNTIME_MARKER not in html:
        raise RuntimeError("Dashboard runtime marker not found; refusing embedded snapshot with ambiguous script order")
    html = html.replace(RUNTIME_MARKER, block + "\n" + RUNTIME_MARKER, 1)

    if EMBEDDED_BOOT_MARKER not in html:
        if BOOT_MARKER not in html:
            raise RuntimeError("Dashboard boot marker not found; refusing embedded snapshot without first-paint render hook")
        html = html.replace(BOOT_MARKER, _boot_hook() + BOOT_MARKER, 1)

    dashboard_path.write_text(html, encoding="utf-8")


if __name__ == "__main__":
    embed()
