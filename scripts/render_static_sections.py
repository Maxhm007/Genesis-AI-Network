from __future__ import annotations

import html
import json
import os
import re
from pathlib import Path
from typing import Any

STATUS = Path("docs/status/status.json")
DASHBOARD = Path("docs/status/index.html")


def esc(value: Any) -> str:
    return html.escape(str(value if value is not None else ""), quote=True)


def safe_url(value: Any) -> str | None:
    url = str(value or "").strip()
    return url if url.startswith(("https://", "http://")) else None


def state_css(value: Any) -> str:
    state = str(value or "").lower()
    if state in {"healthy", "success", "complete", "improved", "at_or_above_reference", "genesis_autonomous"}:
        return "good"
    if state in {"failed", "critical", "regressed"}:
        return "bad"
    return "warn"


def item(title: Any, sub: Any = "", url: Any = None, css: str = "") -> str:
    link = safe_url(url)
    heading = f'<a href="{esc(link)}" target="_blank" rel="noopener"><strong>{esc(title)}</strong></a>' if link else f"<strong>{esc(title)}</strong>"
    safe_css = re.sub(r"[^a-zA-Z0-9_-]", "", css or "")
    return f'<div class="item {safe_css}">{heading}<div class="sub">{esc(sub)}</div></div>'


def empty(message: str) -> str:
    return f'<div class="empty">{esc(message)}</div>'


def replace_content(source: str, element_id: str, content: str) -> str:
    marker = f'id="{element_id}"'
    pos = source.find(marker)
    if pos < 0:
        raise RuntimeError(f"Dashboard section target missing: {element_id}")
    open_start = source.rfind("<", 0, pos)
    open_end = source.find(">", pos)
    if open_start < 0 or open_end < 0:
        raise RuntimeError(f"Dashboard section target malformed: {element_id}")
    tag_match = re.match(r"<([A-Za-z0-9]+)", source[open_start:open_end + 1])
    if not tag_match:
        raise RuntimeError(f"Dashboard section target tag unknown: {element_id}")
    tag = tag_match.group(1)
    close = source.find(f"</{tag}>", open_end + 1)
    if close < 0:
        raise RuntimeError(f"Dashboard section target has no closing tag: {element_id}")
    # These generated target containers are empty before this script runs. Refuse
    # nested existing markup rather than guessing at a boundary.
    existing = source[open_end + 1:close]
    if "<" in existing and f"genesis-static:{element_id}" not in existing:
        raise RuntimeError(f"Dashboard section target unexpectedly contains markup: {element_id}")
    wrapped = f'<!-- genesis-static:{element_id} -->{content}'
    return source[:open_end + 1] + wrapped + source[close:]


def primary_gap(gaps: list[dict[str, Any]]) -> dict[str, Any] | None:
    return next((x for x in gaps if x.get("status") == "measured_below_reference"), None) or next((x for x in gaps if x.get("status") == "unmeasured"), None)


def build_sections(payload: dict[str, Any]) -> dict[str, str]:
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

    focus_rows: list[str] = []
    primary = primary_gap(gaps if isinstance(gaps, list) else [])
    if primary:
        focus_rows.append(item(primary.get("benchmark_id") or "Benchmark gap", f"{str(primary.get('status') or 'unknown').replace('_', ' ')} · {primary.get('family') or 'family'} · capability {primary.get('capability_key') or 'unknown'} · target {primary.get('target_path') or 'unknown'}", css=state_css(primary.get("status"))))
    if active:
        row = active[0]
        focus_rows.append(item(row.get("capability_key") or "Capability growth", f"{row.get('state') or 'unknown'} · {row.get('benchmark_id') or 'benchmark'} · generation {row.get('generation') or '—'}", css=state_css(row.get("state"))))
    if targets:
        row = targets[0]
        focus_rows.append(item(row.get("title") or "Operational target", f"{row.get('severity') or 'unknown'} · {row.get('status') or 'unknown'} · {row.get('module') or 'unknown'}"))

    gap_html = "".join(item(row.get("benchmark_id") or "benchmark", f"{str(row.get('status') or 'unknown').replace('_', ' ')} · {row.get('family') or 'family'} · {row.get('actual_score') if row.get('actual_score') is not None else 'unmeasured'} / {row.get('reference_score') or '—'} {row.get('unit') or ''} · capability {row.get('capability_key') or 'unknown'}", css=state_css(row.get("status"))) for row in gaps)
    growth_html = "".join(item(row.get("capability_key") or "Capability growth", f"{row.get('state') or 'unknown'} · {row.get('benchmark_id') or 'benchmark'} · generation {row.get('generation') or '—'} · {row.get('target_path') or ''}", css=state_css(row.get("state"))) for row in active)
    strategy_html = "".join(item(f"Strategy change {i+1}", row, css="warn") for i, row in enumerate(directives))
    impact_html = "".join(item(row.get("benchmark_id") or "benchmark", f"{str(row.get('status') or 'unknown').replace('_', ' ')} · baseline {row.get('baseline_score') if row.get('baseline_score') is not None else '—'} · current {row.get('current_score') if row.get('current_score') is not None else '—'} · delta {row.get('delta') if row.get('delta') is not None else '—'}", css=state_css(row.get("status"))) for row in impacts)
    activity_html = "".join(item(row.get("message") or "Activity", f"{row.get('date') or 'unknown time'} · {row.get('author') or 'Genesis'}", row.get("url")) for row in activity)
    targets_html = "".join(item(row.get("title") or "Issue", f"{row.get('severity') or 'unknown'} · {row.get('status') or 'unknown'} · {row.get('module') or 'unknown'} · generation {row.get('generation') or '—'}") for row in targets)
    task_html = "".join(f'<div class="stat"><b>{esc(value)}</b><span>{esc(key)}</span></div>' for key, value in tasks.items())
    peer_html = "".join(f'<div class="peer"><div class="peerTop"><div class="peerName"><span class="dot {state_css(row.get("state"))}"></span>Gene {esc(row.get("node") or "—")}</div><span class="pill {state_css(row.get("state"))}">{esc(row.get("state") or "unknown")}</span></div><div class="work">{esc(row.get("workflow") or row.get("label") or "No workflow evidence")}</div><div class="time">{esc(row.get("updated_at") or "unknown")}</div></div>' for row in nodes)
    pr_html = "".join(item(f"#{row.get('number') or '—'} {row.get('title') or 'Candidate PR'}", f"{'merged' if row.get('merged') else row.get('state') or 'unknown'} · {row.get('head') or 'unknown'} · {row.get('updated_at') or 'unknown'}", row.get("url"), state_css("complete" if row.get("merged") else row.get("state"))) for row in prs)
    main_history = sde.get("recent_genesis_authored_main") or []
    promoted = sde.get("recent_improvements") or []
    auto_main = "".join(item(row.get("title") or row.get("message") or "Genesis self-development", f"{row.get('author') or 'Genesis AI'} · {row.get('authored_at') or 'unknown'} · {str(row.get('sha') or '')[:10]}", row.get("url"), "good") for row in main_history)
    auto_promoted = "".join(item(f"[{str(row.get('attribution') or 'unknown').replace('_', ' ')}] #{row.get('number') or '—'} {row.get('title') or 'Development'}", f"{row.get('improvement') or ''} · {row.get('merged_at') or 'unknown'}", row.get("url"), state_css(row.get("attribution"))) for row in promoted)

    return {
        "focus": "".join(focus_rows) or empty("No current focus evidence."),
        "latestActivity": "".join(item(row.get("message") or "Activity", f"{row.get('date') or 'unknown time'} · {row.get('author') or 'Genesis'}", row.get("url")) for row in activity[:5]) or empty("No recent activity."),
        "activity": activity_html or empty("No recent activity."),
        "gapList": gap_html or empty("No benchmark-family evidence parsed yet."),
        "growthList": growth_html or empty("No active capability-growth task. A validated measured deficit is required before growth code is created."),
        "strategyList": strategy_html or empty("No repeated failure pattern currently requires a forced strategy change."),
        "impactList": impact_html or empty("No completed capability-growth task has post-promotion benchmark impact yet."),
        "targets": targets_html or empty("No structured open operational target."),
        "taskStats": task_html or empty("No task data."),
        "peerGrid": peer_html or empty("No peer evidence in this snapshot."),
        "prs": pr_html or empty("No recent candidate PRs."),
        "autoMainHistory": auto_main or empty("No Genesis-authored self-development commit found in this snapshot."),
        "autoPromotionHistory": auto_promoted or empty("No attributed candidate-PR promotion evidence in this snapshot."),
        "autoDefinition": esc(sde.get("definition") or "Strict autonomous credit requires Genesis initiation, independent validation and confirmed promotion on main."),
    }


def render(status_path: Path = STATUS, dashboard_path: Path = DASHBOARD) -> None:
    payload = json.loads(status_path.read_text(encoding="utf-8"))
    source = dashboard_path.read_text(encoding="utf-8")
    for element_id, content in build_sections(payload).items():
        if element_id.startswith("auto") and f'id="{element_id}"' not in source:
            continue
        source = replace_content(source, element_id, content)
    build = f"Build {os.environ.get('GITHUB_SHA', 'local')[:10]} · run {os.environ.get('GITHUB_RUN_ID', 'local')} · static-first / live-enhanced"
    source = replace_content(source, "buildMeta", esc(build))
    report = esc(((payload.get("hourly_report") or {}).get("text") or "No hourly report available."))
    source = replace_content(source, "report", report)
    dashboard_path.write_text(source, encoding="utf-8")


if __name__ == "__main__":
    render()
