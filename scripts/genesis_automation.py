from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import urllib.error
import urllib.request

from genesis.automation import GenesisAutomationModule
from genesis.operations import GenesisOperations


ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "runtime"


def _github_request(method: str, path: str, payload: dict | None = None):
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    repo = os.environ.get("GITHUB_REPOSITORY", "").strip()
    if not token or not repo:
        return None
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        f"https://api.github.com/repos/{repo}{path}",
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "Content-Type": "application/json",
            "User-Agent": "Genesis-AI-Network",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            body = response.read().decode("utf-8")
            return json.loads(body) if body else {}
    except urllib.error.HTTPError as exc:
        print(f"GitHub escalation HTTP {exc.code}: {exc.read().decode('utf-8', errors='replace')[:500]}")
        return None
    except Exception as exc:
        print(f"GitHub escalation unavailable: {type(exc).__name__}: {exc}")
        return None


def evaluate() -> dict:
    operations = GenesisOperations(ROOT).report()
    report = GenesisAutomationModule(ROOT, max_autonomous_attempts=2).evaluate(operations)
    print(json.dumps(report, sort_keys=True))
    return report


def sync_escalations(report: dict | None = None) -> dict:
    report = report or json.loads((RUNTIME / "automation_report.json").read_text(encoding="utf-8"))
    operations = {row["issue_key"]: row for row in GenesisOperations(ROOT).report().get("issues", [])}
    existing = _github_request("GET", "/issues?state=all&per_page=100") or []
    by_key = {}
    marker_prefix = "<!-- genesis-chatgpt-escalation:"
    for issue in existing:
        if "pull_request" in issue:
            continue
        body = str(issue.get("body") or "")
        if marker_prefix in body:
            key = body.split(marker_prefix, 1)[1].split(" -->", 1)[0].strip()
            by_key[key] = issue

    created, updated, closed = [], [], []
    for decision in report.get("decisions", []):
        key = str(decision.get("issue_key", ""))
        current = by_key.get(key)
        item = operations.get(key, {})
        action = decision.get("action")
        if action == "resolved":
            if current and current.get("state") != "closed":
                changed = _github_request("PATCH", f"/issues/{current['number']}", {"state": "closed"})
                if changed:
                    closed.append(current["number"])
            continue
        if action != "escalate_chatgpt":
            continue

        marker = f"<!-- genesis-chatgpt-escalation:{key} -->"
        body = (
            f"{marker}\n"
            "Genesis could not resolve this issue within its bounded autonomous repair budget and requests ChatGPT engineering assistance.\n\n"
            f"- **Operational issue:** {item.get('title', decision.get('title'))}\n"
            f"- **Severity:** {item.get('severity', 'unknown')}\n"
            f"- **Module:** `{item.get('module_id', 'unknown')}`\n"
            f"- **Evidence:** {item.get('evidence', 'Unavailable')}\n"
            f"- **Recommended remediation:** {item.get('remediation', 'Investigate safely.')}\n"
            f"- **Genesis attempts:** {decision.get('attempts')}\n"
            f"- **Task:** `{decision.get('task_id')}`\n"
            f"- **Task state:** `{decision.get('task_state')}`\n"
            f"- **Escalation reason:** {decision.get('reason')}\n\n"
            "## Required handling\n"
            "Inspect repository state and relevant workflow evidence, apply only the smallest safe fix, and preserve the Genesis Constitution, Genesis Block, validation quorum, Security boundaries, owner control, signing policy, and secret boundaries. Do not close this issue until the fix is validated or the remaining blocker is explicitly documented.\n"
        )
        if current is None:
            made = _github_request("POST", "/issues", {
                "title": f"[Genesis Escalation] {item.get('title', decision.get('title'))}",
                "body": body,
            })
            if made:
                created.append(made.get("number"))
        else:
            patch = {"body": body}
            if current.get("state") == "closed":
                patch["state"] = "open"
            changed = _github_request("PATCH", f"/issues/{current['number']}", patch)
            if changed:
                updated.append(current["number"])

    result = {"status": "ok", "created": created, "updated": updated, "closed": closed}
    (RUNTIME / "chatgpt_escalation_sync.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, sort_keys=True))
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Genesis bounded automation and ChatGPT escalation")
    parser.add_argument("action", choices=("evaluate", "sync", "all"))
    args = parser.parse_args()
    report = None
    if args.action in {"evaluate", "all"}:
        report = evaluate()
    if args.action in {"sync", "all"}:
        sync_escalations(report)


if __name__ == "__main__":
    main()
