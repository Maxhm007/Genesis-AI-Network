from __future__ import annotations

import html as html_lib
import json
import re
from pathlib import Path
from typing import Any

STATUS = Path("docs/status/status.json")
DASHBOARD = Path("docs/status/index.html")


def _num(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _replace_text(source: str, element_id: str, value: Any) -> str:
    safe = html_lib.escape(str(value), quote=False)
    pattern = re.compile(
        rf'(<(?P<tag>[A-Za-z0-9]+)\b[^>]*\bid="{re.escape(element_id)}"[^>]*>)(.*?)(</(?P=tag)>)',
        flags=re.S,
    )
    updated, count = pattern.subn(lambda m: m.group(1) + safe + m.group(4), source, count=1)
    if count != 1:
        raise RuntimeError(f"Dashboard first-paint target not found exactly once: {element_id}")
    return updated


def _set_width(source: str, element_id: str, percent: int) -> str:
    pattern = re.compile(rf'(<[A-Za-z0-9]+\b[^>]*\bid="{re.escape(element_id)}"[^>]*)(>)', flags=re.S)

    def repl(match: re.Match[str]) -> str:
        start = match.group(1)
        start = re.sub(r'\sstyle="[^"]*"', '', start, count=1)
        return f'{start} style="width:{max(0, min(100, percent))}%"{match.group(2)}'

    updated, count = pattern.subn(repl, source, count=1)
    if count != 1:
        raise RuntimeError(f"Dashboard progress target not found exactly once: {element_id}")
    return updated


def _primary_gap(gaps: list[dict[str, Any]]) -> dict[str, Any] | None:
    return next((row for row in gaps if row.get("status") == "measured_below_reference"), None) or next(
        (row for row in gaps if row.get("status") == "unmeasured"), None
    )


def values(payload: dict[str, Any]) -> dict[str, str]:
    ce = payload.get("capability_evolution") or {}
    cov = ce.get("coverage") or {}
    growth = ce.get("growth") or {}
    impact = ce.get("impact") or {}
    strategy = ce.get("strategy") or {}
    auto = payload.get("verified_autonomy") or {}
    network = payload.get("network") or {}
    tasks = payload.get("tasks") or {}
    issues = payload.get("issues") or {}
    sde = payload.get("self_development_evaluation") or {}
    attr = sde.get("attribution") or {}
    gaps = ce.get("gaps") or []

    genes = payload.get("genes") or {}
    gene0 = genes.get("0") or genes.get(0) or {}
    health = gene0.get("health") or {}
    gene_name = gene0.get("gene") or "Gene 0"
    state = health.get("state") or "unknown"
    primary = _primary_gap(gaps if isinstance(gaps, list) else [])
    if primary:
        hero_text = (
            f"{primary.get('benchmark_id', 'benchmark')}: "
            f"{str(primary.get('status') or 'unknown').replace('_', ' ')} · "
            f"capability {primary.get('capability_key') or 'unknown'}"
        )
    else:
        hero_text = "No benchmark gap evidence in latest authenticated snapshot"

    measured = _num(cov.get("measured"))
    total = _num(cov.get("total"))
    below = _num(cov.get("below_reference"))
    unmeasured = _num(cov.get("unmeasured"))
    autonomous = _num(auto.get("autonomous_promotions"))
    assisted = _num(auto.get("assisted_promotions"))
    owner = _num(auto.get("owner_promotions"))
    peer_available = _num(network.get("available_peers"))
    peer_total = _num(network.get("total_peers"))

    historical = _num(
        sde.get("historical_autonomous_main_evidence"),
        _num(sde.get("autonomous_pr_promotions"), _num(attr.get("genesis_autonomous"))),
    )
    genesis_main = _num(sde.get("genesis_authored_main_commits"))
    strict = _num(sde.get("strict_verified_cycles"), autonomous)
    attr_assisted = _num(attr.get("assisted"))
    attr_owner = _num(attr.get("owner"))

    generated = str(payload.get("generated_at") or "generated now")
    return {
        "updated": f"Snapshot {generated} · static authenticated evidence",
        "sideUpdated": f"Snapshot {generated}",
        "heroTitle": f"{gene_name} · {state}",
        "heroText": hero_text,
        "heroAuto": str(autonomous),
        "ai": f"{_num(payload.get('ai_capability'))}/100",
        "coverage": f"{measured}/{total}",
        "coverageCap": f"{below} measured below · {unmeasured} unmeasured",
        "growth": str(_num(growth.get("active"))),
        "quarantined": str(_num(strategy.get("quarantined_total"), _num(tasks.get("quarantined")))),
        "strategyCap": f"{_num(strategy.get('directives'))} strategy-change directive(s)",
        "autonomy": str(autonomous),
        "autonomyCap": f"Assisted {assisted} · Owner {owner}",
        "peers": f"{peer_available}/{peer_total}",
        "peersCap": f"{_num(network.get('peer_availability'))}% availability · quorum {network.get('quorum') or '—'}",
        "evMeasured": f"{measured}/{total}",
        "evBelow": str(below),
        "evUnmeasured": str(unmeasured),
        "evNew": str(_num(growth.get("new_capability_tasks"))),
        "evStrategy": str(_num(strategy.get("directives"))),
        "evImproved": str(_num(impact.get("improved"))),
        "iOpen": str(_num(issues.get("open"))),
        "iBlocked": str(_num(issues.get("blocked"))),
        "iResolved": str(_num(issues.get("resolved"))),
        "autoStrict": str(strict),
        "autoPr": str(historical),
        "autoMain": str(genesis_main),
        "autoOther": f"{attr_assisted} / {attr_owner}",
        "autoOtherCap": f"Assisted {attr_assisted} · Owner {attr_owner}",
    }


def render_static(status_path: Path = STATUS, dashboard_path: Path = DASHBOARD) -> dict[str, str]:
    if not status_path.is_file():
        raise RuntimeError(f"Status snapshot not found: {status_path}")
    if not dashboard_path.is_file():
        raise RuntimeError(f"Dashboard not found: {dashboard_path}")

    payload = json.loads(status_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or "generated_at" not in payload:
        raise RuntimeError("Status snapshot is not a generated dashboard payload")

    first_paint = values(payload)
    source = dashboard_path.read_text(encoding="utf-8")
    for element_id, value in first_paint.items():
        # Autonomous Development is injected by the self-evaluation builder. If
        # that optional view is absent, do not break the Overview deployment.
        if element_id.startswith("auto") and f'id="{element_id}"' not in source:
            continue
        source = _replace_text(source, element_id, value)

    source = _set_width(source, "aiBar", _num(payload.get("ai_capability")))

    # The build must never publish the original indefinite-loading first paint.
    if re.search(r'id="heroTitle"[^>]*>\s*Loading Genesis', source):
        raise RuntimeError("Static first paint still contains Loading Genesis")
    if re.search(r'id="ai"[^>]*>\s*[—-]\s*<', source):
        raise RuntimeError("Static first paint still contains an empty AI capability value")

    dashboard_path.write_text(source, encoding="utf-8")
    return first_paint


if __name__ == "__main__":
    print(json.dumps(render_static(), indent=2, sort_keys=True))
