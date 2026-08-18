from __future__ import annotations

import argparse
from email.message import EmailMessage
import json
import os
from pathlib import Path
import smtplib
import ssl
import urllib.error
import urllib.request

from genesis.operations import GenesisOperations
from genesis.scorecard import GenesisScorecard
from genesis.modules.task_queue import PersistentTaskQueue
from genesis.task_lifecycle import TaskLifecycleReconciler


ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "runtime"


def _load_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


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
    output = {"scorecard": scorecard, "task_lifecycle": lifecycle, **result}
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


def sync_github_issues(operations_report: dict) -> dict:
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    repo = os.environ.get("GITHUB_REPOSITORY", "").strip()
    if not token or not repo:
        return {"status": "skipped", "reason": "GitHub token/repository unavailable"}

    existing = _github_request("GET", "/issues?state=all&per_page=100") or []
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
            "Gene 0 keeps this issue active until the measured condition disappears. New repair work is generated when previous work ends but the issue remains. Repairs still use the bounded task → candidate → test → Security → validator path."
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

    result = {"status": "ok", "created": created, "updated": updated, "closed": closed}
    (RUNTIME / "github_issue_sync.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result


def render_email() -> tuple[str, str]:
    scorecard = _load_json(RUNTIME / "system_scorecard.json", {})
    operations = GenesisOperations(ROOT)
    ops = operations.report()
    queue = PersistentTaskQueue(RUNTIME / "genesis_tasks.sqlite3")
    states = {state: len(queue.list(state=state, limit=1000)) for state in ("new", "assigned", "running", "blocked", "review", "complete", "failed", "quarantined")}
    ai = scorecard.get("ai_capability_score", {})
    eff = scorecard.get("efficiency_score", {})
    mission = scorecard.get("immortality_research_progress_score", {})

    open_items = [x for x in ops.get("issues", []) if x.get("status") in {"open", "blocked"}]
    resolved_items = [x for x in ops.get("issues", []) if x.get("status") == "resolved"]
    subject = f"Genesis Hourly Update — AI {ai.get('score', 'Unmeasured')} | Open {len(open_items)} | Blocked {ops.get('blocked', 0)}"

    lines = [
        "Genesis Hourly Operations Report", "Generated and sent by Gene 0 from GitHub Actions.", "",
        "KPI DASHBOARD",
        f"AI Capability: {ai.get('score', 'Unmeasured')}/{ai.get('max_score', 100)}",
        f"Efficiency: {eff.get('score', 'Unmeasured')}/{eff.get('max_score', 100)} | samples={eff.get('samples', 0)} | capability/compute={eff.get('capability_per_compute', 0)}",
        f"Immortality Research Progress: {mission.get('score', 'Unmeasured')}/{mission.get('max_score', 100)} (evidence-pipeline maturity, not percent immortality achieved)",
        f"Persistent tasks: {json.dumps(states, sort_keys=True)}",
        f"Issue history events: {ops.get('history_events', 0)}", "",
        f"ISSUES: open={ops.get('open', 0)} blocked={ops.get('blocked', 0)} resolved={ops.get('resolved', 0)}",
    ]
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

    lines += ["", "AUTONOMOUS ISSUE POLICY",
        "Gene 0 owns the issue lifecycle. Every detection, observation, repair task, reopen and resolution is kept in append-only history. If a repair task ends but the measured issue remains, Gene creates the next work generation instead of forgetting the issue. No repair may bypass tests, Security review, independent validation, protected files, signing boundaries, or owner-only secrets."]
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
        report = collect(); print(json.dumps({"detected": len(report.get("issues", [])), "created_tasks": report.get("created_tasks", []), "history_events": report.get("history_events", 0), "task_lifecycle": report.get("task_lifecycle", {})}, sort_keys=True))
    if args.action in {"sync-issues", "all"}:
        print(json.dumps(sync_github_issues(GenesisOperations(ROOT).report()), sort_keys=True))
    if args.action in {"email", "all"}:
        send_email()


if __name__ == "__main__":
    main()
