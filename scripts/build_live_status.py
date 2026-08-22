from __future__ import annotations

import base64
import json
import os
import re
import urllib.error
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


def safe_api(path: str, default: Any) -> Any:
    try:
        return api(path)
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, ValueError):
        return default


def report_text(body: str) -> str:
    match = re.search(r"```(?:text)?\n([\s\S]*?)```", body or "", re.I)
    return (match.group(1) if match else body or "").strip()


def _integer(text: str, pattern: str, default: int = 0) -> int:
    match = re.search(pattern, text, re.I)
    return int(match.group(1)) if match else default


def _float_or_none(value: str) -> float | None:
    value = value.strip()
    if value.lower() in {"none", "null", "unmeasured", "unknown", ""}:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def parse_hourly(text: str) -> dict[str, Any]:
    ai = _integer(text, r"AI Capability:\s*(\d+)\/100")
    efficiency = _integer(text, r"Efficiency:\s*(\d+)\/100")
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

    coverage = {"measured": 0, "total": 0, "below_reference": 0, "unmeasured": 0, "at_or_above": 0}
    match = re.search(
        r"Benchmark coverage:\s*measured=(\d+)\/(\d+)\s*\|\s*below_reference=(\d+)\s*\|\s*unmeasured=(\d+)\s*\|\s*at_or_above=(\d+)",
        text,
        re.I,
    )
    if match:
        coverage = {
            "measured": int(match.group(1)),
            "total": int(match.group(2)),
            "below_reference": int(match.group(3)),
            "unmeasured": int(match.group(4)),
            "at_or_above": int(match.group(5)),
        }

    growth = {"active": 0, "complete": 0, "quarantined": 0, "new_capability_tasks": 0}
    match = re.search(
        r"Capability growth:\s*active=(\d+)\s*\|\s*complete=(\d+)\s*\|\s*quarantined=(\d+)\s*\|\s*new_capability_tasks=(\d+)",
        text,
        re.I,
    )
    if match:
        growth = {
            "active": int(match.group(1)),
            "complete": int(match.group(2)),
            "quarantined": int(match.group(3)),
            "new_capability_tasks": int(match.group(4)),
        }

    impact = {"improved": 0, "no_gain": 0, "regressed": 0, "awaiting": 0}
    match = re.search(
        r"Post-promotion impact:\s*improved=(\d+)\s*\|\s*no_gain=(\d+)\s*\|\s*regressed=(\d+)\s*\|\s*awaiting=(\d+)",
        text,
        re.I,
    )
    if match:
        impact = {
            "improved": int(match.group(1)),
            "no_gain": int(match.group(2)),
            "regressed": int(match.group(3)),
            "awaiting": int(match.group(4)),
        }

    strategy = {"directives": 0, "quarantined_total": tasks.get("quarantined", 0)}
    match = re.search(r"Strategy-change directives:\s*(\d+)\s*\|\s*quarantined_total=(\d+)", text, re.I)
    if match:
        strategy = {"directives": int(match.group(1)), "quarantined_total": int(match.group(2))}

    attribution = {"autonomous": 0, "assisted": 0, "owner": 0, "proven_cycles": 0}
    match = re.search(
        r"Development attribution:\s*autonomous=(\d+)\s*\|\s*assisted=(\d+)\s*\|\s*owner=(\d+)\s*\|\s*proven_cycles=(\d+)",
        text,
        re.I,
    )
    if match:
        attribution = {
            "autonomous": int(match.group(1)),
            "assisted": int(match.group(2)),
            "owner": int(match.group(3)),
            "proven_cycles": int(match.group(4)),
        }

    gaps: list[dict[str, Any]] = []
    gap_re = re.compile(
        r"^- \[GAP:([^\]]+)\] ([^|\n]+) \| family=([^|\n]+) \| actual=([^|\n]+) \| reference=([^ ]+) ([^|\n]+) \| capability=([^|\n]+) \| target=([^\n]+)$",
        re.I | re.M,
    )
    for match in gap_re.finditer(text):
        gaps.append({
            "status": match.group(1).strip().lower(),
            "benchmark_id": match.group(2).strip(),
            "family": match.group(3).strip(),
            "actual_score": _float_or_none(match.group(4)),
            "reference_score": _float_or_none(match.group(5)),
            "unit": match.group(6).strip(),
            "capability_key": match.group(7).strip(),
            "target_path": match.group(8).strip(),
        })

    active_growth: list[dict[str, Any]] = []
    growth_re = re.compile(
        r"^- \[GROWTH:([^\]]+)\] ([^|\n]+) \| benchmark=([^|\n]+) \| capability=([^|\n]+) \| generation=([^|\n]+) \| target=([^\n]+)$",
        re.I | re.M,
    )
    for match in growth_re.finditer(text):
        active_growth.append({
            "state": match.group(1).strip().lower(),
            "task_id": match.group(2).strip(),
            "benchmark_id": match.group(3).strip(),
            "capability_key": match.group(4).strip(),
            "generation": match.group(5).strip(),
            "target_path": match.group(6).strip(),
        })

    new_capabilities: list[dict[str, Any]] = []
    new_re = re.compile(
        r"^- \[NEW-CAPABILITY:([^\]]+)\] ([^|\n]+) \| capability=([^|\n]+) \| target=([^\n]+)$",
        re.I | re.M,
    )
    for match in new_re.finditer(text):
        new_capabilities.append({
            "state": match.group(1).strip().lower(),
            "task_id": match.group(2).strip(),
            "capability_key": match.group(3).strip(),
            "target_path": match.group(4).strip(),
        })

    strategy_directives = [
        line.strip()
        for line in re.findall(r"^- Strategy change:\s*(.+)$", text, re.I | re.M)
        if line.strip()
    ]

    impacts: list[dict[str, Any]] = []
    impact_re = re.compile(
        r"^- \[IMPACT:([^\]]+)\] ([^|\n]+) \| capability=([^|\n]+) \| baseline=([^|\n]+) \| current=([^|\n]+) \| delta=([^|\n]+) \| growth_task=([^\n]+)$",
        re.I | re.M,
    )
    for match in impact_re.finditer(text):
        impacts.append({
            "status": match.group(1).strip().lower(),
            "benchmark_id": match.group(2).strip(),
            "capability_key": match.group(3).strip(),
            "baseline_score": _float_or_none(match.group(4)),
            "current_score": _float_or_none(match.group(5)),
            "delta": _float_or_none(match.group(6)),
            "growth_task_id": match.group(7).strip(),
        })

    return {
        "ai_capability": ai,
        "efficiency": efficiency,
        "issues": issues,
        "tasks": tasks,
        "targets": targets,
        "capability_evolution": {
            "coverage": coverage,
            "growth": growth,
            "impact": impact,
            "strategy": strategy,
            "development_attribution": attribution,
            "gaps": gaps,
            "active_growth_tasks": active_growth,
            "new_capabilities": new_capabilities,
            "strategy_directives": strategy_directives,
            "impact_assessments": impacts,
        },
    }


def is_solution(message: str) -> bool:
    """Detect useful engineering commits without claiming autonomous attribution."""
    positive = (
        "Genesis self-development candidate",
        "adaptive self-learning feedback loop",
        "dynamic Genesis AI score",
        "bounded cycle budget utility",
        "runtime health snapshot helper",
        "advanced_reasoning",
        "self learning",
        "adaptive learning",
        "failure-learning",
        "learn from failed attempts",
        "new capability",
        "capability evolution",
        "benchmark-driven capability",
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


def solution_from_commit(commit: dict[str, Any]) -> dict[str, Any]:
    message = str(commit.get("commit", {}).get("message", "")).splitlines()[0]
    return {
        "message": re.sub(r"^Genesis self-development candidate:\s*", "", message, flags=re.I),
        "url": commit.get("html_url"),
        "date": commit.get("commit", {}).get("author", {}).get("date"),
        "author": commit.get("commit", {}).get("author", {}).get("name"),
        "sha": commit.get("sha"),
    }


def run_success_rate(runs: list[dict[str, Any]], pattern: str | None = None) -> tuple[int, int, int]:
    selected = []
    for run in runs:
        if pattern and not re.search(pattern, str(run.get("name", "")), re.I):
            continue
        if run.get("status") == "completed":
            selected.append(run)
    selected = selected[:20]
    if not selected:
        return 0, 0, 0
    successful = sum(1 for run in selected if run.get("conclusion") == "success")
    return round(successful * 100 / len(selected)), successful, len(selected)


def node_health_from_runs(node: str, repo: str, runs: list[dict[str, Any]]) -> dict[str, Any]:
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


def node_metadata(repo: str) -> dict[str, Any]:
    payload = safe_api(f"/repos/{OWNER}/{repo}/contents/node.json", {})
    content = payload.get("content") if isinstance(payload, dict) else None
    if not content:
        return {}
    try:
        return json.loads(base64.b64decode(content).decode("utf-8"))
    except (ValueError, json.JSONDecodeError, UnicodeDecodeError):
        return {}


def gene_snapshot(node: str, repo: str) -> dict[str, Any]:
    runs_payload = safe_api(f"/repos/{OWNER}/{repo}/actions/runs?per_page=40", {"workflow_runs": []})
    runs = runs_payload.get("workflow_runs", []) if isinstance(runs_payload, dict) else []
    commits = safe_api(f"/repos/{OWNER}/{repo}/commits?per_page=40", [])
    issues_payload = safe_api(f"/repos/{OWNER}/{repo}/issues?state=all&per_page=100", [])
    issues_only = [item for item in issues_payload if "pull_request" not in item] if isinstance(issues_payload, list) else []

    workflow_rate, workflow_ok, workflow_total = run_success_rate(runs)
    heal_rate, heal_ok, heal_total = run_success_rate(runs, r"Self Healing|Peer Healing")
    dev_rate, dev_ok, dev_total = run_success_rate(runs, r"Proactive Development|Autonomy Trial|Candidate|Gene Pulse")

    solution_commits = [
        commit for commit in commits
        if is_solution(str(commit.get("commit", {}).get("message", "")).splitlines()[0])
    ] if isinstance(commits, list) else []
    solution_count = len(solution_commits)
    last_solution = solution_from_commit(solution_commits[0]) if solution_commits else None

    recent_activity = []
    if isinstance(commits, list):
        for commit in commits:
            message = str(commit.get("commit", {}).get("message", "")).splitlines()[0]
            if re.search(
                r"Genesis self-development candidate|adaptive self-learning|dynamic Genesis AI score|runtime health snapshot|bounded cycle budget|advanced_reasoning|failure|capability|benchmark|Record validated Genesis update on blockchain|peer heal|self heal|Gene Pulse",
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
            if len(recent_activity) >= 10:
                break

    open_issues = sum(1 for item in issues_only if item.get("state") == "open")
    closed_issues = sum(1 for item in issues_only if item.get("state") == "closed")
    total_issues = open_issues + closed_issues
    closure_rate = round(closed_issues * 100 / total_issues) if total_issues else 100

    # Evidence-based dashboard composite, not the official Genesis AI capability score.
    solution_component = min(100, solution_count * 20)
    self_dev_index = round((0.45 * workflow_rate) + (0.30 * heal_rate) + (0.25 * solution_component))

    health = node_health_from_runs(node, repo, runs)
    metadata = node_metadata(repo)

    return {
        "node": node,
        "gene": f"Gene {node}",
        "repo": repo,
        "health": health,
        "metadata": metadata,
        "kpis": {
            "self_development_index": self_dev_index,
            "workflow_success_rate": workflow_rate,
            "workflow_successful": workflow_ok,
            "workflow_samples": workflow_total,
            "healing_success_rate": heal_rate,
            "healing_successful": heal_ok,
            "healing_samples": heal_total,
            "development_success_rate": dev_rate,
            "development_successful": dev_ok,
            "development_samples": dev_total,
            "solution_commits": solution_count,
            "pending_issues": open_issues,
            "solved_issues": closed_issues,
            "issue_closure_rate": closure_rate,
            "total_issues": total_issues,
        },
        "last_solution": last_solution,
        "recent_activity": recent_activity,
    }


def main() -> None:
    comments = safe_api(f"/repos/{OWNER}/{REPOS['0']}/issues/4/comments?per_page=100", [])
    hourly_comment = next(
        (comment for comment in reversed(comments) if "Genesis Hourly Update" in str(comment.get("body", ""))),
        comments[-1] if comments else {},
    )
    hourly_text = report_text(str(hourly_comment.get("body", "")))
    parsed = parse_hourly(hourly_text)

    genes = {node: gene_snapshot(node, repo) for node, repo in REPOS.items()}
    nodes = [genes[node]["health"] for node in REPOS]

    healthy_peers = sum(1 for item in nodes if item.get("state") in {"healthy", "working"})
    total_peers = len(nodes)
    peer_availability = round(healthy_peers * 100 / total_peers) if total_peers else 0

    commits = safe_api(f"/repos/{OWNER}/{REPOS['0']}/commits?per_page=40", [])
    solution_commit = next(
        (
            commit
            for commit in commits
            if is_solution(str(commit.get("commit", {}).get("message", "")).splitlines()[0])
        ),
        None,
    )
    last_solution = solution_from_commit(solution_commit) if solution_commit else None
    recent_activity = genes["0"]["recent_activity"]

    pulls = safe_api(f"/repos/{OWNER}/{REPOS['0']}/pulls?state=all&sort=updated&direction=desc&per_page=20", [])
    candidate_prs = []
    for pr in pulls:
        ref = str(pr.get("head", {}).get("ref", ""))
        title = str(pr.get("title", ""))
        if ref.startswith("genesis/candidate-") or "Genesis autonomous candidate" in title or "capability" in title.lower():
            candidate_prs.append(
                {
                    "number": pr.get("number"),
                    "title": title,
                    "state": pr.get("state"),
                    "merged": bool(pr.get("merged_at")),
                    "head": ref,
                    "updated_at": pr.get("updated_at"),
                    "url": pr.get("html_url"),
                }
            )
        if len(candidate_prs) >= 8:
            break

    total_pending = sum(gene["kpis"]["pending_issues"] for gene in genes.values())
    total_solved = sum(gene["kpis"]["solved_issues"] for gene in genes.values())
    network_self_dev = round(sum(gene["kpis"]["self_development_index"] for gene in genes.values()) / len(genes))

    capability = parsed.get("capability_evolution", {})
    attribution = capability.get("development_attribution", {})

    payload = {
        "schema_version": 2,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": "authenticated GitHub Actions snapshot",
        "hourly_report": {
            "created_at": hourly_comment.get("created_at"),
            "updated_at": hourly_comment.get("updated_at"),
            "url": hourly_comment.get("html_url"),
            "text": hourly_text,
        },
        **parsed,
        "network": {
            "total_peers": total_peers,
            "available_peers": healthy_peers,
            "unavailable_peers": total_peers - healthy_peers,
            "peer_availability": peer_availability,
            "quorum_ready": healthy_peers >= 2,
            "quorum": f"{healthy_peers}/{total_peers}",
            "self_development_index": network_self_dev,
            "pending_issues": total_pending,
            "solved_issues": total_solved,
        },
        "verified_autonomy": {
            "autonomous_promotions": attribution.get("autonomous", 0),
            "assisted_promotions": attribution.get("assisted", 0),
            "owner_promotions": attribution.get("owner", 0),
            "proven_cycles": attribution.get("proven_cycles", 0),
        },
        "genes": genes,
        "nodes": nodes,
        "last_solution": last_solution,
        "recent_activity": recent_activity,
        "candidate_prs": candidate_prs,
        "metric_notes": {
            "ai_capability": "Official competitive engineering score. Unmeasured benchmark families receive no frontier credit.",
            "verified_autonomy": "Counts only proven cycles reported by the Genesis autonomy-proof ledger; owner and assisted work are separate.",
            "self_development_index": (
                "Dashboard-only composite of recent workflow reliability, healing reliability and solution-commit evidence. "
                "It is not the official AI capability score and does not establish autonomous attribution."
            ),
            "capability_growth": (
                "Unmeasured benchmarks are evidence gaps. Capability-growth code is valid only after a validated below-reference measurement, "
                "and promotion counts as improvement only after post-promotion remeasurement."
            ),
        },
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        f"Wrote {OUT} with AI={parsed['ai_capability']}, measured_benchmarks={capability.get('coverage', {}).get('measured', 0)}, "
        f"active_growth={capability.get('growth', {}).get('active', 0)}, peer_availability={peer_availability}%"
    )


if __name__ == "__main__":
    main()
