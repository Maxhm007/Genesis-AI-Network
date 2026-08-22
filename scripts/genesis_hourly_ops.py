from __future__ import annotations

import argparse
from collections import Counter
from email.message import EmailMessage
import json
import os
from pathlib import Path
import re
import smtplib
import ssl
import urllib.error
import urllib.request

from genesis.capability_evolution import CapabilityEvolutionController
from genesis.operations import GenesisOperations
from genesis.scorecard import GenesisScorecard
from genesis.modules.task_queue import PersistentTaskQueue
from genesis.self_evaluation import GenesisSelfEvaluation
from genesis.task_lifecycle import TaskLifecycleReconciler


ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "runtime"
ACTIVE_GROWTH_STATES = {"new", "assigned", "running", "paused", "blocked", "review", "failed"}


def _load_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _task_gap(task) -> dict:
    payload = dict(getattr(task, "payload", {}) or {})
    direct = payload.get("benchmark_gap")
    if isinstance(direct, dict):
        return dict(direct)
    discovery = payload.get("discovery")
    if isinstance(discovery, dict):
        finding = discovery.get("finding")
        if isinstance(finding, dict) and isinstance(finding.get("benchmark_gap"), dict):
            return dict(finding["benchmark_gap"])
    return {}


def _is_new_capability_task(task) -> bool:
    payload = dict(getattr(task, "payload", {}) or {})
    if bool(payload.get("new_capability")):
        return True
    discovery = payload.get("discovery")
    if isinstance(discovery, dict):
        finding = discovery.get("finding")
        if isinstance(finding, dict) and bool(finding.get("new_capability")):
            return True
    finding = payload.get("finding")
    return isinstance(finding, dict) and bool(finding.get("new_capability"))


def capability_evolution_snapshot(queue: PersistentTaskQueue | None = None) -> dict:
    """Return dashboard-safe evidence for benchmark-driven capability evolution.

    A missing benchmark is reported as an evidence gap. Only a validated
    below-reference result is reported as a measured capability deficit. This
    function is read-only: it never creates work or changes score.
    """
    queue = queue or PersistentTaskQueue(RUNTIME / "genesis_tasks.sqlite3")
    controller = CapabilityEvolutionController(ROOT, queue=queue)
    gaps = controller.benchmark_gaps()
    quarantine = controller.quarantine_analysis()
    impacts = controller.impact_assessments(gaps)
    tasks = queue.list(limit=5000)

    growth = [task for task in tasks if task.payload.get("task_type") == "capability_growth"]
    measurements = [task for task in tasks if task.payload.get("task_type") == "frontier_benchmark_measurement"]
    new_capability = [task for task in tasks if _is_new_capability_task(task)]

    growth_states = Counter(task.state for task in growth)
    measurement_states = Counter(task.state for task in measurements)
    impact_states = Counter(str(item.get("status") or "unknown") for item in impacts)

    active_growth = []
    for task in growth:
        if task.state not in ACTIVE_GROWTH_STATES:
            continue
        gap = _task_gap(task)
        active_growth.append({
            "task_id": task.task_id,
            "state": task.state,
            "benchmark_id": gap.get("benchmark_id"),
            "capability_key": task.payload.get("capability_key") or gap.get("capability_key"),
            "generation": task.payload.get("capability_generation") or task.payload.get("work_generation") or 1,
            "target_path": task.payload.get("target_path") or gap.get("target_path"),
            "last_error": task.last_error,
        })
    active_growth.sort(key=lambda item: (str(item.get("benchmark_id") or ""), str(item.get("task_id") or "")))

    new_capability_rows = []
    for task in new_capability:
        gap = _task_gap(task)
        new_capability_rows.append({
            "task_id": task.task_id,
            "state": task.state,
            "capability_key": task.payload.get("capability_key") or gap.get("capability_key"),
            "target_path": task.payload.get("target_path") or gap.get("target_path") or "genesis/learned_capabilities.py",
        })

    return {
        "status": "ok",
        "benchmark_total": len(gaps),
        "measured": sum(1 for gap in gaps if gap.get("status") != "unmeasured"),
        "measured_below_reference": sum(1 for gap in gaps if gap.get("status") == "measured_below_reference"),
        "unmeasured": sum(1 for gap in gaps if gap.get("status") == "unmeasured"),
        "at_or_above_reference": sum(1 for gap in gaps if gap.get("status") == "at_or_above_reference"),
        "gaps": gaps,
        "growth_states": dict(growth_states),
        "growth_active": len(active_growth),
        "active_growth_tasks": active_growth,
        "measurement_states": dict(measurement_states),
        "new_capability_tasks": len(new_capability_rows),
        "new_capability_rows": new_capability_rows[:10],
        "quarantine_analysis": quarantine,
        "impact_counts": dict(impact_states),
        "impact_assessments": impacts,
    }


def development_attribution_snapshot() -> dict:
    try:
        report = GenesisSelfEvaluation(ROOT).report(limit=10)
        attribution = dict(report.get("development_attribution") or {})
        return {
            "status": "ok",
            "genesis_autonomous": int(attribution.get("genesis_autonomous", 0) or 0),
            "assisted": int(attribution.get("assisted", 0) or 0),
            "owner": int(attribution.get("owner", 0) or 0),
            "total_proven_cycles": int(attribution.get("total_proven_cycles", 0) or 0),
            "recent_autonomous_improvements": report.get("recent_autonomous_improvements", []),
        }
    except Exception as exc:
        return {"status": "unavailable", "error": f"{type(exc).__name__}: {exc}"[:1000]}


def collect() -> dict:
    lifecycle = TaskLifecycleReconciler(ROOT).reconcile()
    scorecard_path = RUNTIME / "system_scorecard.json"
    if scorecard_path.exists():
        scorecard = _load_json(scorecard_path, {})
    else:
        scorecard = GenesisScorecard(ROOT).write(scorecard_path)
    operations = GenesisOperations(ROOT)
    detected = operations.detect(scorecard)
    result = operations.persist_and_queue(detected)
    try:
        capability = capability_evolution_snapshot()
    except Exception as exc:
        capability = {"status": "unavailable", "error": f"{type(exc).__name__}: {exc}"[:1000]}
    attribution = development_attribution_snapshot()
    output = {
        "scorecard": scorecard,
        "task_lifecycle": lifecycle,
        "capability_evolution": capability,
        "development_attribution": attribution,
        **result,
    }
    (RUNTIME / "hourly_operations.json").write_text(json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return output


def _github_request(method: str, path: str, payload: dict | None = None):
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    repo = os.environ.get("GITHUB_REPOSITORY", "").strip()
    if not token or not repo:
        return None
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        f"https://api.github.com/repos/{repo}{path}", data=data, method=method,
        headers={
            "Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28", "Content-Type": "application/json",
            "User-Agent": "Genesis-AI-Network",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            body = response.read().decode("utf-8")
            return json.loads(body) if body else {}
    except urllib.error.HTTPError as exc:
        print(f"GitHub issue sync HTTP {exc.code}: {exc.read().decode('utf-8', errors='replace')[:500]}")
        return None
    except Exception as exc:
        print(f"GitHub issue sync unavailable: {type(exc).__name__}: {exc}")
        return None


def _body_field(body: str, label: str, default: str = "") -> str:
    match = re.search(rf"^- \*\*{re.escape(label)}:\*\*\s*(.*)$", body, re.MULTILINE)
    return match.group(1).strip() if match else default


def _recover_resolved_github_history(existing_github_issues: list[dict], operations_report: dict) -> int:
    """Recover lost resolved tombstones from the durable GitHub issue mirror."""
    operations = GenesisOperations(ROOT)
    ledger: dict[str, dict] = {}
    if operations.ledger_path.exists():
        for line in operations.ledger_path.read_text(encoding="utf-8").splitlines():
            try:
                row = json.loads(line)
                ledger[str(row["issue_key"])] = row
            except Exception:
                continue

    ledger_titles = {str(row.get("title", "")).strip() for row in ledger.values()}
    active_titles = {
        str(row.get("title", "")).strip()
        for row in operations_report.get("issues", [])
        if row.get("status") in {"open", "blocked"}
    }
    recovered = 0

    for issue in existing_github_issues:
        if "pull_request" in issue:
            continue
        body = str(issue.get("body") or "")
        marker_match = re.search(r"<!-- genesis-ops:([^ ]+) -->", body)
        if not marker_match or _body_field(body, "Status").lower() != "resolved":
            continue
        key = marker_match.group(1).strip()
        title = str(issue.get("title") or "").removeprefix("[Genesis Ops] ").strip()
        if key in ledger or title in ledger_titles or title in active_titles:
            continue

        resolved_at = str(issue.get("closed_at") or issue.get("updated_at") or issue.get("created_at") or "")
        row = {
            "issue_key": key,
            "title": title or "Recovered Genesis operational issue",
            "severity": _body_field(body, "Severity", "unknown"),
            "module_id": _body_field(body, "Module", "genesis.operations").strip("`"),
            "status": "resolved",
            "evidence": _body_field(body, "Evidence", "Recovered from durable GitHub issue history."),
            "remediation": _body_field(body, "Remediation", ""),
            "owner_action_required": _body_field(body, "Owner action required", "False").lower() == "true",
            "first_seen_at": _body_field(body, "First seen", ""),
            "last_seen_at": _body_field(body, "Last seen", ""),
            "resolved_at": resolved_at,
            "recovered_from_github_issue": issue.get("number"),
        }
        operations._append_history(
            "recovered_resolved",
            key,
            title=row["title"],
            github_issue=issue.get("number"),
            resolved_at=resolved_at,
        )
        row["history_snapshot"] = operations.history(key, limit=operations.EMBEDDED_HISTORY_LIMIT)
        ledger[key] = row
        ledger_titles.add(row["title"])
        recovered += 1

    if recovered:
        ordered = sorted(
            ledger.values(),
            key=lambda row: (row.get("status") == "resolved", row.get("severity", ""), row.get("first_seen_at", "")),
        )
        operations.ledger_path.write_text(
            "".join(json.dumps(row, sort_keys=True) + "\n" for row in ordered),
            encoding="utf-8",
        )
    return recovered


def sync_github_issues(operations_report: dict) -> dict:
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    repo = os.environ.get("GITHUB_REPOSITORY", "").strip()
    if not token or not repo:
        return {"status": "skipped", "reason": "GitHub token/repository unavailable"}

    existing = _github_request("GET", "/issues?state=all&per_page=100") or []
    recovered = _recover_resolved_github_history(existing, operations_report)
    if recovered:
        operations_report = GenesisOperations(ROOT).report()

    by_key = {}
    for issue in existing:
        if "pull_request" in issue:
            continue
        body = str(issue.get("body") or "")
        marker = "<!-- genesis-ops:"
        if marker in body:
            key = body.split(marker, 1)[1].split(" -->", 1)[0].strip()
            by_key[key] = issue

    created, updated, closed = [], [], []
    for item in operations_report.get("issues", []):
        key = item["issue_key"]
        marker = f"<!-- genesis-ops:{key} -->"
        history = GenesisOperations(ROOT).history(key, limit=10)
        history_lines = "\n".join(
            f"- {event.get('at','')} | {event.get('event')} | task={event.get('task_id','')}"
            for event in history[-10:]
        ) or "- No history yet."
        body = (
            f"{marker}\nAutomated Genesis operational issue.\n\n"
            f"- **Severity:** {item.get('severity')}\n"
            f"- **Module:** `{item.get('module_id')}`\n"
            f"- **Status:** {item.get('status')}\n"
            f"- **Evidence:** {item.get('evidence')}\n"
            f"- **Remediation:** {item.get('remediation')}\n"
            f"- **Owner action required:** {item.get('owner_action_required', False)}\n"
            f"- **First seen:** {item.get('first_seen_at', '')}\n"
            f"- **Last seen:** {item.get('last_seen_at', '')}\n"
            f"- **Work generation:** {item.get('work_generation', 0)}\n\n"
            f"### Gene issue history\n{history_lines}\n\n"
            "Gene 0 keeps this issue active until the measured condition disappears. New work is generated when previous work ends but the issue remains. Repairs and development still use bounded candidate → test → Security → independent validator → promotion gates."
        )
        current = by_key.get(key)
        desired_state = "closed" if item.get("status") == "resolved" else "open"
        if current is None and desired_state == "open":
            created_issue = _github_request("POST", "/issues", {"title": f"[Genesis Ops] {item.get('title')}", "body": body})
            if created_issue:
                created.append(created_issue.get("number"))
        elif current is not None:
            patch = {"body": body}
            if current.get("state") != desired_state:
                patch["state"] = desired_state
            changed = _github_request("PATCH", f"/issues/{current['number']}", patch)
            if changed:
                (closed if desired_state == "closed" else updated).append(current["number"])

    result = {"status": "ok", "created": created, "updated": updated, "closed": closed, "recovered_resolved": recovered}
    (RUNTIME / "github_issue_sync.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result


def format_capability_evolution_lines(snapshot: dict) -> list[str]:
    if snapshot.get("status") != "ok":
        return ["CAPABILITY EVOLUTION", f"- Unavailable: {snapshot.get('error', 'unknown error')}"]

    lines = ["CAPABILITY EVOLUTION", "Benchmark gaps and evidence:"]
    for gap in snapshot.get("gaps", []):
        actual = "unmeasured" if gap.get("actual_score") is None else str(gap.get("actual_score"))
        lines.append(
            f"- [GAP:{str(gap.get('status','unknown')).upper()}] {gap.get('benchmark_id')} | "
            f"family={gap.get('family')} | actual={actual} | reference={gap.get('reference_score')} {gap.get('unit')} | "
            f"capability={gap.get('capability_key')} | target={gap.get('target_path')}"
        )

    lines += ["", "Active capability growth:"]
    active = snapshot.get("active_growth_tasks", [])
    if active:
        for task in active[:12]:
            lines.append(
                f"- [GROWTH:{str(task.get('state','unknown')).upper()}] {task.get('task_id')} | "
                f"benchmark={task.get('benchmark_id')} | capability={task.get('capability_key')} | "
                f"generation={task.get('generation')} | target={task.get('target_path')}"
            )
    else:
        lines.append("- None. Measured deficits are required before capability-growth code is created.")

    lines += ["", "New learned capability work:"]
    learned = snapshot.get("new_capability_rows", [])
    if learned:
        for task in learned[:8]:
            lines.append(
                f"- [NEW-CAPABILITY:{str(task.get('state','unknown')).upper()}] {task.get('task_id')} | "
                f"capability={task.get('capability_key')} | target={task.get('target_path')}"
            )
    else:
        lines.append("- No active or historical new-capability task detected in the current queue snapshot.")

    lines += ["", "Strategy changes from quarantine learning:"]
    directives = (snapshot.get("quarantine_analysis") or {}).get("strategy_directives", [])
    if directives:
        for directive in directives[:4]:
            lines.append(f"- Strategy change: {directive}")
    else:
        lines.append("- No repeated failure pattern currently requires a forced strategy change.")

    lines += ["", "Post-promotion benchmark impact:"]
    impacts = snapshot.get("impact_assessments", [])
    if impacts:
        for item in impacts[:10]:
            lines.append(
                f"- [IMPACT:{str(item.get('status','unknown')).upper()}] {item.get('benchmark_id')} | "
                f"capability={item.get('capability_key')} | baseline={item.get('baseline_score')} | "
                f"current={item.get('current_score')} | delta={item.get('delta')} | growth_task={item.get('growth_task_id')}"
            )
    else:
        lines.append("- No completed capability-growth task is awaiting or reporting post-promotion impact yet.")
    return lines


def render_email() -> tuple[str, str]:
    scorecard = _load_json(RUNTIME / "system_scorecard.json", {})
    operations = GenesisOperations(ROOT)
    ops = operations.report()
    queue = PersistentTaskQueue(RUNTIME / "genesis_tasks.sqlite3")
    states = {state: len(queue.list(state=state, limit=1000)) for state in ("new", "assigned", "running", "paused", "blocked", "review", "complete", "failed", "quarantined")}
    ai = scorecard.get("ai_capability_score", {})
    eff = scorecard.get("efficiency_score", {})
    mission = scorecard.get("immortality_research_progress_score", {})
    try:
        capability = capability_evolution_snapshot(queue)
    except Exception as exc:
        capability = {"status": "unavailable", "error": f"{type(exc).__name__}: {exc}"[:1000]}
    attribution = development_attribution_snapshot()

    open_items = [x for x in ops.get("issues", []) if x.get("status") in {"open", "blocked"}]
    resolved_items = [x for x in ops.get("issues", []) if x.get("status") == "resolved"]
    subject = (
        f"Genesis Hourly Update — AI {ai.get('score', 'Unmeasured')} | "
        f"Gaps {capability.get('measured_below_reference', 0)}/{capability.get('unmeasured', 0)} | "
        f"Open {len(open_items)}"
    )

    impact_counts = capability.get("impact_counts", {}) if capability.get("status") == "ok" else {}
    quarantine = capability.get("quarantine_analysis", {}) if capability.get("status") == "ok" else {}
    growth_states = capability.get("growth_states", {}) if capability.get("status") == "ok" else {}
    lines = [
        "Genesis Hourly Operations Report", "Generated and sent by Gene 0 from GitHub Actions.", "",
        "KPI DASHBOARD",
        f"AI Capability: {ai.get('score', 'Unmeasured')}/{ai.get('max_score', 100)}",
        f"Efficiency: {eff.get('score', 'Unmeasured')}/{eff.get('max_score', 100)} | samples={eff.get('samples', 0)} | capability/compute={eff.get('capability_per_compute', 0)}",
        f"Immortality Research Progress: {mission.get('score', 'Unmeasured')}/{mission.get('max_score', 100)} (evidence-pipeline maturity, not percent immortality achieved)",
        f"Benchmark coverage: measured={capability.get('measured', 0)}/{capability.get('benchmark_total', 0)} | below_reference={capability.get('measured_below_reference', 0)} | unmeasured={capability.get('unmeasured', 0)} | at_or_above={capability.get('at_or_above_reference', 0)}",
        f"Capability growth: active={capability.get('growth_active', 0)} | complete={growth_states.get('complete', 0)} | quarantined={growth_states.get('quarantined', 0)} | new_capability_tasks={capability.get('new_capability_tasks', 0)}",
        f"Post-promotion impact: improved={impact_counts.get('improved', 0)} | no_gain={impact_counts.get('no_measured_gain', 0)} | regressed={impact_counts.get('regressed', 0)} | awaiting={impact_counts.get('awaiting_post_promotion_measurement', 0)}",
        f"Strategy-change directives: {len(quarantine.get('strategy_directives', []))} | quarantined_total={quarantine.get('quarantined_tasks', states.get('quarantined', 0))}",
        f"Development attribution: autonomous={attribution.get('genesis_autonomous', 0)} | assisted={attribution.get('assisted', 0)} | owner={attribution.get('owner', 0)} | proven_cycles={attribution.get('total_proven_cycles', 0)}",
        f"Persistent tasks: {json.dumps(states, sort_keys=True)}",
        f"Issue history events: {ops.get('history_events', 0)}", "",
    ]

    lines.extend(format_capability_evolution_lines(capability))
    lines += ["", f"ISSUES: open={ops.get('open', 0)} blocked={ops.get('blocked', 0)} resolved={ops.get('resolved', 0)}"]
    if open_items:
        for item in open_items:
            lines.append(f"- [{item.get('severity','?').upper()}] {item.get('title')} | {item.get('status')} | module={item.get('module_id')} | work_generation={item.get('work_generation', 0)}")
            lines.append(f"  Evidence: {item.get('evidence')}")
            lines.append(f"  Next: {item.get('remediation')}")
            recent = operations.history(item.get("issue_key"), limit=3)
            for event in recent:
                lines.append(f"  History: {event.get('at','')} | {event.get('event')} | task={event.get('task_id','')}")
    else:
        lines.append("- No unresolved operational issues recorded.")

    lines += ["", "RESOLVED ISSUE HISTORY"]
    for item in resolved_items[-10:]:
        lines.append(f"- {item.get('title')} | resolved_at={item.get('resolved_at', 'unknown')}")
    if not resolved_items:
        lines.append("- None recorded yet.")

    lines += ["", "AUTONOMOUS EVIDENCE POLICY",
        "Gene 0 keeps issue and capability work durable across generations. Unmeasured benchmarks are evidence gaps, not proof of weakness. Capability-growth work requires a validated below-reference measurement. A promoted candidate does not count as capability improvement until the same benchmark is measured again. No work may bypass tests, Security review, independent validation, protected files, signing boundaries, or owner-only secrets."]
    return subject, "\n".join(lines) + "\n"


def send_email() -> dict:
    sender = os.environ.get("GENESIS_EMAIL_FROM", "").strip()
    recipient = os.environ.get("GENESIS_EMAIL_TO", "").strip() or sender
    username = os.environ.get("GENESIS_SMTP_USERNAME", "").strip()
    password = os.environ.get("GENESIS_SMTP_APP_PASSWORD", "").strip()
    if not sender or not recipient or not username or not password:
        result = {"status": "blocked", "reason": "Missing GitHub mail secrets", "required": ["GENESIS_EMAIL_FROM", "GENESIS_EMAIL_TO", "GENESIS_SMTP_USERNAME", "GENESIS_SMTP_APP_PASSWORD"]}
        (RUNTIME / "email_delivery_status.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(result)); return result
    subject, body = render_email()
    msg = EmailMessage(); msg["From"] = sender; msg["To"] = recipient; msg["Subject"] = subject; msg.set_content(body)
    context = ssl.create_default_context()
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=30, context=context) as smtp:
        smtp.login(username, password); smtp.send_message(msg)
    result = {"status": "sent", "from": sender, "to": recipient, "subject": subject}
    (RUNTIME / "email_delivery_status.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result)); return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Genesis GitHub-native hourly operations")
    parser.add_argument("action", choices=("collect", "sync-issues", "email", "all")); args = parser.parse_args()
    if args.action in {"collect", "all"}:
        report = collect(); print(json.dumps({
            "detected": len(report.get("issues", [])),
            "created_tasks": report.get("created_tasks", []),
            "history_events": report.get("history_events", 0),
            "task_lifecycle": report.get("task_lifecycle", {}),
            "capability_evolution": report.get("capability_evolution", {}),
            "development_attribution": report.get("development_attribution", {}),
        }, sort_keys=True))
    if args.action in {"sync-issues", "all"}:
        print(json.dumps(sync_github_issues(GenesisOperations(ROOT).report()), sort_keys=True))
    if args.action in {"email", "all"}:
        send_email()


if __name__ == "__main__":
    main()
