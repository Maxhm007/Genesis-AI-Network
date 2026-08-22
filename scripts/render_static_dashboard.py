from __future__ import annotations

import html as html_lib
import json
import os
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


def _esc(value: Any) -> str:
    return html_lib.escape(str(value if value is not None else ""), quote=True)


def _safe_url(value: Any) -> str | None:
    url = str(value or "").strip()
    return url if url.startswith(("https://", "http://")) else None


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


def _replace_html(source: str, element_id: str, value: str) -> str:
    pattern = re.compile(
        rf'(<(?P<tag>[A-Za-z0-9]+)\b[^>]*\bid="{re.escape(element_id)}"[^>]*>)(.*?)(</(?P=tag)>)',
        flags=re.S,
    )
    updated, count = pattern.subn(lambda m: m.group(1) + value + m.group(4), source, count=1)
    if count != 1:
        raise RuntimeError(f"Dashboard static-section target not found exactly once: {element_id}")
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


def _item(title: Any, sub: Any = "", url: Any = None, css: str = "") -> str:
    safe_title = _esc(title)
    safe_sub = _esc(sub)
    safe_css = re.sub(r"[^a-zA-Z0-9_-]", "", css or "")
    link = _safe_url(url)
    heading = f'<a href="{_esc(link)}" target="_blank" rel="noopener"><strong>{safe_title}</strong></a>' if link else f"<strong>{safe_title}</strong>"
    return f'<div class="item {safe_css}">{heading}<div class="sub">{safe_sub}</div></div>'


def _empty(message: str) -> str:
    return f'<div class="empty">{_esc(message)}</div>'


def _state_css(value: Any) -> str:
    state = str(value or "").lower()
    if state in {"healthy", "success", "complete", "improved", "at_or_above_reference", "genesis_autonomous"}:
        return "good"
    if state in {"failed", "critical", "regressed"}:
        return "bad"
    return "warn"


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
    build_sha = os.environ.get("GITHUB_SHA", "local")[:10]
    run_id = os.environ.get("GITHUB_RUN_ID", "local")
    return {
        "updated": f"Snapshot {generated} · static authenticated evidence",
        "sideUpdated": f"Snapshot {generated}",
        "buildMeta": f"Build {build_sha} · run {run_id} · static-first / live-enhanced",
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


def sections(payload: dict[str, Any]) -> dict[str, str]:
    ce = payload.get("capability_evolution") or {}
    gaps = ce.get("gaps") or []
    active = ce.get("active_growth_tasks") or []
    directives = ce.get("strategy_directives") or []
    impacts = ce.get("impact_assessments") or []
    targets = payload.get("targets") or []
    activity = payload.get("recent_activity") or []
    tasks = payload.get("tasks") or {}
    nodes = payload.get("nodes") or []
    prs = payload.get("candidate_prs") or []
    sde = payload.get("self_development_evaluation") or {}

    primary = _primary_gap(gaps if isinstance(gaps, list) else [])
    focus: list[str] = []
    if primary:
        focus.append(
            _item(
                primary.get("benchmark_id") or "Benchmark gap",
                f"{str(primary.get('status') or 'unknown').replace('_', ' ')} · {primary.get('family') or 'family'} · capability {primary.get('capability_key') or 'unknown'} · target {primary.get('target_path') or 'unknown'}",
                css=_state_css(primary.get("status")),
            )
        )
    if active:
        row = active[0]
        focus.append(_item(row.get("capability_key") or "Capability growth", f"{row.get('state') or 'unknown'} · {row.get('benchmark_id') or 'benchmark'} · generation {row.get('generation') or '—'}", css=_state_css(row.get("state"))))
    if targets:
        row = targets[0]
        focus.append(_item(row.get("title") or "Operational target", f"{row.get('severity') or 'unknown'} · {row.get('status') or 'unknown'} · {row.get('module') or 'unknown'}"))

    gap_html = "".join(
        _item(
            row.get("benchmark_id") or "benchmark",
            f"{str(row.get('status') or 'unknown').replace('_', ' ')} · {row.get('family') or 'family'} · {row.get('actual_score') if row.get('actual_score') is not None else 'unmeasured'} / {row.get('reference_score') or '—'} {row.get('unit') or ''} · capability {row.get('capability_key') or 'unknown'}",
            css=_state_css(row.get("status")),
        )
        for row in gaps
    )
    growth_html = "".join(
        _item(row.get("capability_key") or "Capability growth", f"{row.get('state') or 'unknown'} · {row.get('benchmark_id') or 'benchmark'} · generation {row.get('generation') or '—'} · {row.get('target_path') or ''}", css=_state_css(row.get("state")))
        for row in active
    )
    strategy_html = "".join(_item(f"Strategy change {i + 1}", row, css="warn") for i, row in enumerate(directives))
    impact_html = "".join(
        _item(row.get("benchmark_id") or "benchmark", f"{str(row.get('status') or 'unknown').replace('_', ' ')} · baseline {row.get('baseline_score') if row.get('baseline_score') is not None else '—'} · current {row.get('current_score') if row.get('current_score') is not None else '—'} · delta {row.get('delta') if row.get('delta') is not None else '—'}", css=_state_css(row.get("status")))
        for row in impacts
    )
    activity_html = "".join(_item(row.get("message") or "Activity", f"{row.get('date') or 'unknown time'} · {row.get('author') or 'Genesis'}", row.get("url")) for row in activity)
    target_html = "".join(_item(row.get("title") or "Issue", f"{row.get('severity') or 'unknown'} · {row.get('status') or 'unknown'} · {row.get('module') or 'unknown'} · generation {row.get('generation') or '—'}") for row in targets)
    task_html = "".join(f'<div class="stat"><b>{_esc(value)}</b><span>{_esc(key)}</span></div>' for key, value in tasks.items())
    peer_html = "".join(
        f'<div class="peer"><div class="peerTop"><div class="peerName"><span class="dot {_state_css(row.get("state"))}"></span>Gene {_esc(row.get("node") or "—")}</div><span class="pill {_state_css(row.get("state"))}">{_esc(row.get("state") or "unknown")}</span></div><div class="work">{_esc(row.get("workflow") or row.get("label") or "No workflow evidence")}</div><div class="time">{_esc(row.get("updated_at") or "unknown")}</div>{f'<a href="{_esc(_safe_url(row.get("url")))}" target="_blank" rel="noopener">Open workflow ↗</a>' if _safe_url(row.get("url")) else ''}</div>'
        for row in nodes
    )
    pr_html = "".join(_item(f"#{row.get('number') or '—'} {row.get('title') or 'Candidate PR'}", f"{'merged' if row.get('merged') else row.get('state') or 'unknown'} · {row.get('head') or 'unknown'} · {row.get('updated_at') or 'unknown'}", row.get("url"), _state_css("complete" if row.get("merged") else row.get("state"))) for row in prs)
    main_history = sde.get("recent_genesis_authored_main") or []
    promotion_history = sde.get("recent_improvements") or []
    auto_main_html = "".join(_item(row.get("title") or row.get("message") or "Genesis self-development", f"{row.get('author') or 'Genesis AI'} · {row.get('authored_at') or 'unknown'} · {str(row.get('sha') or '')[:10]}", row.get("url"), "good") for row in main_history)
    auto_promotion_html = "".join(_item(f"[{str(row.get('attribution') or 'unknown').replace('_', ' ')}] #{row.get('number') or '—'} {row.get('title') or 'Development'}", f"{row.get('improvement') or ''} · {row.get('merged_at') or 'unknown'}", row.get("url"), _state_css(row.get("attribution"))) for row in promotion_history)

    return {
        "focus": "".join(focus) or _empty("No current focus evidence."),
        "latestActivity": "".join(_item(row.get("message") or "Activity", f"{row.get('date') or 'unknown time'} · {row.get('author') or 'Genesis'}", row.get("url")) for row in activity[:5]) or _empty("No recent activity."),
        "activity": activity_html or _empty("No recent activity."),
        "gapList": gap_html or _empty("No benchmark-family evidence parsed yet."),
        "growthList": growth_html or _empty("No active capability-growth task. A validated measured deficit is required before growth code is created."),
        "strategyList": strategy_html or _empty("No repeated failure pattern currently requires a forced strategy change."),
        "impactList": impact_html or _empty("No completed capability-growth task has post-promotion benchmark impact yet."),
        "targets": target_html or _empty("No structured open operational target."),
        "taskStats": task_html or _empty("No task data."),
        "peerGrid": peer_html or _empty("No peer evidence in this snapshot."),
        "prs": pr_html or _empty("No recent candidate PRs."),
        "autoMainHistory": auto_main_html or _empty("No Genesis-authored self-development commit found in the current evidence snapshot."),
        "autoPromotionHistory": auto_promotion_html or _empty("No attributed candidate-PR promotion evidence in this snapshot."),
        "autoDefinition": _esc(sde.get("definition") or "Strict autonomous credit requires Genesis initiation, independent validation and confirmed promotion on main."),
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
        if element_id.startswith("auto") and f'id="{element_id}"' not in source:
            continue
        if element_id == "buildMeta" and f'id="{element_id}"' not in source:
            continue
        source = _replace_text(source, element_id, value)

    for element_id, fragment in sections(payload).items():
        if f'id="{element_id}"' not in source:
            if element_id.startswith("auto"):
                continue
            raise RuntimeError(f"Required static dashboard section missing: {element_id}")
        source = _replace_html(source, element_id, fragment)

    report_text = ((payload.get("hourly_report") or {}).get("text") or "No hourly report available.")
    source = _replace_text(source, "report", report_text)
    source = _set_width(source, "aiBar", _num(payload.get("ai_capability")))

    if re.search(r'id="heroTitle"[^>]*>\s*Loading Genesis', source):
        raise RuntimeError("Static first paint still contains Loading Genesis")
    if re.search(r'id="ai"[^>]*>\s*[—-]\s*<', source):
        raise RuntimeError("Static first paint still contains an empty AI capability value")

    dashboard_path.write_text(source, encoding="utf-8")
    return first_paint


if __name__ == "__main__":
    print(json.dumps(render_static(), indent=2, sort_keys=True))
