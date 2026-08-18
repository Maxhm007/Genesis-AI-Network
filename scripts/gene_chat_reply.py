from __future__ import annotations

import json
import os
import re
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHAT_ISSUE = 52
OWNER = "Maxhm007"
PROVIDER = os.environ.get("GENESIS_PROVIDER_URL", "http://127.0.0.1:8766").rstrip("/")


def github(method: str, path: str, payload: dict | None = None):
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    repo = os.environ.get("GITHUB_REPOSITORY", "").strip()
    if not token or not repo:
        raise RuntimeError("GITHUB_TOKEN and GITHUB_REPOSITORY are required")
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
            "User-Agent": "Genesis-Gene-Chat",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        body = response.read().decode("utf-8")
        return json.loads(body) if body else {}


def provider(prompt: str) -> str:
    request = urllib.request.Request(
        f"{PROVIDER}/reason",
        data=json.dumps({"prompt": prompt}).encode("utf-8"),
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=210) as response:
        payload = json.loads(response.read().decode("utf-8"))
    return str(payload.get("response", "")).strip()


def latest_hourly_context() -> str:
    comments = github("GET", "/issues/4/comments?per_page=100") or []
    for comment in reversed(comments):
        body = str(comment.get("body") or "")
        if "Genesis Hourly Update" in body:
            return body[-9000:]
    return "No current hourly report was available."


def operational_facts(report: str) -> str:
    ai = re.search(r"AI Capability:\s*(\d+)\/100", report, re.I)
    eff = re.search(r"Efficiency:\s*(\d+)\/100", report, re.I)
    issues = re.search(r"ISSUES:\s*open=(\d+)\s+blocked=(\d+)\s+resolved=(\d+)", report, re.I)
    target = re.search(r"- \[(\w+)\] ([^|\n]+) \| ([^|\n]+) \| module=([^|\n]+)", report)
    facts = []
    if ai:
        facts.append(f"AI capability: {ai.group(1)}/100")
    if eff:
        facts.append(f"Efficiency: {eff.group(1)}/100")
    if issues:
        facts.append(f"Operational issues: open={issues.group(1)}, blocked={issues.group(2)}, resolved={issues.group(3)}")
    if target:
        facts.append(
            f"Current top target: {target.group(2).strip()} | severity={target.group(1)} | "
            f"status={target.group(3).strip()} | module={target.group(4).strip()}"
        )
    return "\n".join(facts) or "No structured operational facts were parsed."


def recent_chat_context() -> str:
    comments = github("GET", f"/issues/{CHAT_ISSUE}/comments?per_page=30") or []
    rows = []
    for item in comments[-12:]:
        login = str((item.get("user") or {}).get("login") or "unknown")
        body = str(item.get("body") or "").replace("<!-- genesis-gene-reply:v1 -->", "").strip()
        rows.append(f"{login}: {body[:1600]}")
    return "\n\n".join(rows)


def main() -> None:
    event_path = Path(os.environ.get("GITHUB_EVENT_PATH", ""))
    if not event_path.exists():
        raise SystemExit("GitHub event payload unavailable")
    event = json.loads(event_path.read_text(encoding="utf-8"))
    issue = event.get("issue") or {}
    comment = event.get("comment") or {}
    author = str((comment.get("user") or {}).get("login") or "")
    body = str(comment.get("body") or "").strip()

    if int(issue.get("number", 0)) != CHAT_ISSUE:
        print("Ignoring non-chat issue")
        return
    if author != OWNER or not body:
        print("Ignoring non-owner or empty chat prompt")
        return
    if "genesis-gene-reply:v1" in body:
        print("Ignoring Genesis reply marker")
        return

    report = latest_hourly_context()
    facts = operational_facts(report)
    prompt = f"""
You are Gene 0, the coordinator of Genesis AI Network, replying to the repository owner in the dedicated Gene Chat thread.
Use the structured facts below as authoritative for current operational state. Use the full report only for supporting detail.
Be concise, operational, and transparent. Never invent a current target, score, solved issue, or task state.
Never claim a task is complete unless the evidence shows it. If the user asks for a change, explain what Genesis can do through its normal bounded task -> candidate -> tests -> Security -> independent validators path. Do not imply you can bypass protected files, secrets, permissions, or validation.

USER MESSAGE:
{body[:5000]}

CURRENT OPERATIONAL FACTS:
{facts}

LATEST GENESIS OPERATIONS REPORT:
{report}

RECENT GENE CHAT:
{recent_chat_context()}

Reply as Gene 0 in plain text. Prefer 2-6 short paragraphs or concise bullets when useful.
""".strip()

    try:
        answer = provider(prompt)
    except Exception as exc:
        answer = (
            "I received your message, but my local reasoning provider was unavailable for this reply. "
            f"The communication channel is healthy; provider error: {type(exc).__name__}."
        )

    answer = answer.strip() or "I received your message, but I did not produce a usable reply."
    github(
        "POST",
        f"/issues/{CHAT_ISSUE}/comments",
        {"body": f"<!-- genesis-gene-reply:v1 -->\n**Gene 0**\n\n{answer[:12000]}"},
    )
    print("Posted Gene 0 chat reply")


if __name__ == "__main__":
    main()
