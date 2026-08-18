from __future__ import annotations

import json
import os
import re
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

OWNER = "Maxhm007"
REPOS = {
    "0": "Genesis-AI-Network",
    "2": "Genesis-Node-2",
    "3": "Genesis-Node-3",
}
OUT = Path("docs/status/status.json")
TOKEN = os.environ.get("GITHUB_TOKEN", "").strip()


def api(path: str) -> Any:
    req = urllib.request.Request(
        f"https://api.github.com{path}",
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "genesis-live-status-builder",
            **({"Authorization": f"Bearer {TOKEN}"} if TOKEN else {}),
        },
    )
    with urllib.request.urlopen(req, timeout=30) as response:
        return json.load(response)


def report_text(body: str) -> str:
    match = re.search(r"```(?:text)?\n([\s\S]*?)```", body or "", re.I)
    return (match.group(1) if match else body or "").strip()


def parse_hourly(text: str) -> dict[str, Any]:
    def integer(pattern: str) -> int:
        match = re.search(pattern, text, re.I)
        return int(match.group(1)) if match else 0

    ai = integer(r"AI Capability:\s*(\d+)\/100")
    efficiency = integer(r"Efficiency:\s*(\d+)\/100")
    issue_match = re.search(r"ISSUES:\s*open=(\d+)\s+blocked=(\d+)\s+resolved=(\d+)", text, re.I)
    issues = {
        "open": int(issue_match.group(1)) if issue_match else 0,
        "blocked": int(issue_match.group(2)) if issue_match else 0,
        "resolved": int(issue_match.group(3)) if issue_match else 0,
    }

    tasks: dict[str, Any] = {}
    task_match = re.search(r"Persistent tasks:\s*(\{[^\n]+\})", text, re.I)
    if task_match:
        try:
            tasks = json.loads(task_match.group(1))
        except json.JSONDecodeError:
            tasks = {}

    targets: list[dict[str, str]] = []
    target_re = re.compile(
        r"- \[(\w+)\] ([^|\n]+) \| ([^|\n]+) \| module=([^|\n]+)(?: \| work_generation=(\d+))?"
    )
    for match in target_re.finditer(text):
        targets.append(
            {
                "severity": match.group(1).strip(),
                "title": match.group(2).strip(),
                "status": match.group(3).strip(),
                "module": match.group(4).strip(),
                "generation": (match.group(5) or "").strip(),
            }
        )

    return {
        "ai_capability": ai,
        "efficiency": efficiency,
        "issues": issues,
        "tasks": tasks,
        "targets": targets,
    }


def node_health(node: str, repo: str) -> dict[str, Any]:
    data = api(f"/repos/{OWNER}/{repo}/actions/runs?per_page=15")
    runs = data.get("workflow_runs", [])
    preferred = next(
        (
            run
            for run in runs
            if re.search(
                r"Self Healing|Peer Healing|Gene Pulse|Proactive Development|Gene Registry|attest",
                str(run.get("name", "")),
                re.I,
            )
        ),
        runs[0] if runs else None,
    )
    if not preferred:
        return {"node": node, "repo": repo, "state": "unknown", "label": "No workflow evidence"}

    if preferred.get("status") != "completed":
        state = "working"
    elif preferred.get("conclusion") == "success":
        state = "healthy"
    else:
        state = "failed"

    return {
        "node": node,
        "repo": repo,
        "state": state,
        "workflow": preferred.get("name"),
        "status": preferred.get("status"),
        "conclusion": preferred.get("conclusion"),
        "updated_at": preferred.get("updated_at"),
        "url": preferred.get("html_url"),
    }


def is_solution(message: str) -> bool:
    positive = (
        "Genesis self-development candidate",
        "adaptive self-learning feedback loop",
        "dynamic Genesis AI score",
        "bounded cycle budget utility",
        "runtime health snapshot helper",
        "advanced_reasoning",
        "self learning",
        "adaptive learning",
    )
    negative = (
        "Record validated Genesis update on blockchain",
        "Publish Genesis blockchain consensus status",
        "candidate PR gate",
        "candidate PR opener",
        "Pages",
        "Test ",
    )
    lower = message.lower()
    return any(item.lower() in lower for item in positive) and not any(item.lower() in lower for item in negative)


def main() -> None:
    comments = api(f"/repos/{OWNER}/{REPOS['0']}/issues/4/comments?per_page=100")
    hourly_comment = next(
        (comment for comment in reversed(comments) if "Genesis Hourly Update" in str(comment.get("body", ""))),
        comments[-1] if comments else {},
    )
    hourly_text = report_text(str(hourly_comment.get("body", "")))
    parsed = parse_hourly(hourly_text)

    commits = api(f"/repos/{OWNER}/{REPOS['0']}/commits?per_page=40")
    recent_activity: list[dict[str, Any]] = []
    for commit in commits:
        message = str(commit.get("commit", {}).get("message", "")).splitlines()[0]
        if re.search(
            r"Genesis self-development candidate|adaptive self-learning|dynamic Genesis AI score|runtime health snapshot|bounded cycle budget|advanced_reasoning|Record validated Genesis update on blockchain|Publish Genesis blockchain consensus status",
            message,
            re.I,
        ):
            recent_activity.append(
                {
                    "message": message,
                    "url": commit.get("html_url"),
                    "date": commit.get("commit", {}).get("author", {}).get("date"),
                    "author": commit.get("commit", {}).get("author", {}).get("name"),
                    "sha": commit.get("sha"),
                }
            )
        if len(recent_activity) >= 8:
            break

    solution_commit = next(
        (
            commit
            for commit in commits
            if is_solution(str(commit.get("commit", {}).get("message", "")).splitlines()[0])
        ),
        None,
    )
    last_solution = None
    if solution_commit:
        message = str(solution_commit.get("commit", {}).get("message", "")).splitlines()[0]
        last_solution = {
            "message": re.sub(r"^Genesis self-development candidate:\s*", "", message, flags=re.I),
            "url": solution_commit.get("html_url"),
            "date": solution_commit.get("commit", {}).get("author", {}).get("date"),
            "author": solution_commit.get("commit", {}).get("author", {}).get("name"),
            "sha": solution_commit.get("sha"),
        }

    pulls = api(f"/repos/{OWNER}/{REPOS['0']}/pulls?state=all&sort=updated&direction=desc&per_page=15")
    candidate_prs = []
    for pr in pulls:
        ref = str(pr.get("head", {}).get("ref", ""))
        title = str(pr.get("title", ""))
        if ref.startswith("genesis/candidate-") or "Genesis autonomous candidate" in title:
            candidate_prs.append(
                {
                    "number": pr.get("number"),
                    "title": title,
                    "state": pr.get("state"),
                    "head": ref,
                    "updated_at": pr.get("updated_at"),
                    "url": pr.get("html_url"),
                }
            )
        if len(candidate_prs) >= 6:
            break

    nodes = []
    for node, repo in REPOS.items():
        try:
            nodes.append(node_health(node, repo))
        except Exception as exc:  # retain the rest of the dashboard if one peer read fails
            nodes.append({"node": node, "repo": repo, "state": "unknown", "label": str(exc)})

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": "authenticated GitHub Actions snapshot",
        "hourly_report": {
            "created_at": hourly_comment.get("created_at"),
            "updated_at": hourly_comment.get("updated_at"),
            "url": hourly_comment.get("html_url"),
            "text": hourly_text,
        },
        **parsed,
        "nodes": nodes,
        "last_solution": last_solution,
        "recent_activity": recent_activity,
        "candidate_prs": candidate_prs,
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Wrote {OUT} with AI={parsed['ai_capability']} and {len(nodes)} node snapshots")


if __name__ == "__main__":
    main()
