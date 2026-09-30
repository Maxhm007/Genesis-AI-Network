from __future__ import annotations

import argparse
import json
import os
import re
import urllib.error
import urllib.request
from pathlib import Path

from genesis.providers import ProviderRegistry

ROOT = Path(__file__).resolve().parents[1]
CONFIG = json.loads((ROOT / "config" / "genesis_teammates.json").read_text(encoding="utf-8"))
REPOSITORY = os.environ.get("GITHUB_REPOSITORY", "").strip()
TOKEN = os.environ.get("GITHUB_TOKEN", "").strip() or os.environ.get("GH_TOKEN", "").strip()
API = "https://api.github.com"
AUTONOMOUS_SOURCE_LABELS = {"genesis-autonomous", "agentic-lab"}
AUTONOMOUS_BLOCKING_LABELS = {"genesis-waiting-capability", "genesis-needs-human"}

ROLE_MAP = {
    "atlas": ("planner", "Architecture and decomposition. Produce a bounded design, dependencies, risks, and handoff in neutral operational language."),
    "forge": ("engineer", "Implementation and repair. Produce the smallest safe implementation path and execution acceptance criteria in neutral operational language."),
    "sentinel": ("validator", "Independent QA and validation. Define pass/fail evidence and reject unsupported completion claims in neutral operational language."),
    "scout": ("researcher", "Research and investigation. Gather repository evidence, unknowns, and the next evidence-producing action in neutral operational language."),
    "recovery": ("reviewer", "Recovery and troubleshooting. Identify why prior attempts failed and require a materially different next strategy in neutral operational language."),
}


def paged_get(path: str) -> list[dict]:
    rows: list[dict] = []
    page = 1
    while page <= 3:
        suffix = "&" if "?" in path else "?"
        batch = request("GET", f"{path}{suffix}per_page=100&page={page}")
        if not isinstance(batch, list):
            break
        rows.extend(batch)
        if len(batch) < 100:
            break
        page += 1
    return rows


def issue_comments(issue_number: int) -> list[dict]:
    return paged_get(f"/issues/{issue_number}/comments")


def open_development_issues() -> list[dict]:
    protected = set(int(v) for v in CONFIG.get("workspaces", {}).values())
    rows = paged_get("/issues?state=open")
    out: list[dict] = []
    for issue in rows:
        number = int(issue.get("number") or 0)
        if number in protected or not is_autonomous_issue(issue):
            continue
        out.append(issue)
    return out


def is_autonomous_issue(issue: dict) -> bool:
    labels = {
        str(item.get("name") or "") if isinstance(item, dict) else str(item)
        for item in (issue.get("labels") or [])
    }
    title = str(issue.get("title") or "")
    body = str(issue.get("body") or "")
    return (
        str(issue.get("state") or "open").lower() == "open"
        and not issue.get("pull_request")
        and bool(labels & AUTONOMOUS_SOURCE_LABELS)
        and not bool(labels & AUTONOMOUS_BLOCKING_LABELS)
        and not title.startswith(("[Genesis Teammate]", "[Nexus Task]"))
        and "<!-- genesis-team-task -->" not in body
        and "<!-- genesis-team-evolution -->" not in body
    )


def autonomous_claim_exists(issue_number: int) -> bool:
    marker = f"<!-- genesis-team-autonomous-claim:{issue_number} -->"
    return any(marker in str(row.get("body") or "") for row in issue_comments(issue_number))


def select_autonomous_issue() -> dict | None:
    candidates = []
    for issue in open_development_issues():
        number = int(issue.get("number") or 0)
        if number <= 0 or autonomous_claim_exists(number):
            continue
        labels = {
            str(item.get("name") or "") if isinstance(item, dict) else str(item)
            for item in (issue.get("labels") or [])
        }
        score = 0
        if "critical" in labels:
            score += 100
        if "owner-priority" in labels or "owner_priority" in labels:
            score += 80
        if "bug" in labels:
            score += 30
        if "genesis-autonomous" in labels:
            score += 20
        if "agentic-lab" in labels:
            score += 10
        created = str(issue.get("created_at") or "")
        candidates.append((score, created, issue))
    if not candidates:
        return None
    candidates.sort(key=lambda row: (-row[0], row[1]))
    return candidates[0][2]


def autonomous_development(run_id: str) -> None:
    if not CONFIG.get("rules", {}).get("team_can_work_independently_for_genesis_development", False):
        return
    nexus_issue = int(CONFIG["workspaces"]["nexus"])
    issue = select_autonomous_issue()
    if issue is None:
        comment(
            nexus_issue,
            f"<!-- genesis-team-autonomous-idle:{run_id} -->\n"
            "### Autonomous team pulse\nNo unclaimed actionable Genesis development issue was found.",
        )
        return

    number = int(issue["number"])
    title = str(issue.get("title") or f"Issue #{number}")
    body = str(issue.get("body") or "").strip()
    objective = (
        f"Autonomous Genesis development task from issue #{number}: {title}. "
        + (f"Context: {body[:4000]}" if body else "")
    ).strip()
    agent = classify(objective)
    workspace = int(CONFIG["workspaces"][agent])
    workflow = str(CONFIG["workflows"][agent])
    marker = f"<!-- genesis-team-autonomous-claim:{number} -->"

    dispatch(
        workflow,
        {
            "objective": objective[:10000],
            "source_comment_id": f"autonomous-{number}-{run_id}",
            "nexus_issue": str(nexus_issue),
            "source_issue": str(number),
        },
    )
    comment(
        number,
        f"{marker}\n"
        f"### Nexus autonomous team claim\n"
        f"- **Assigned teammate:** {agent.title()} (workspace #{workspace})\n"
        f"- **Nexus:** #{nexus_issue}\n"
        "- **Mode:** independent Genesis development\n"
        "- **Rule:** existing Agentic Lab, validation, and issue-closure authorities remain authoritative.",
    )
    comment(
        nexus_issue,
        f"<!-- genesis-team-autonomous-route:{run_id}:{number} -->\n"
        "### Autonomous Genesis development\n"
        f"- **Source issue:** #{number} — {title}\n"
        f"- **Assigned teammate:** {agent.title()} (workspace #{workspace})\n"
        "- **Status:** delegated without owner prompt",
    )
    comment(
        workspace,
        f"<!-- genesis-team-autonomous-assignment:{number} -->\n"
        "### Autonomous assignment from Nexus\n"
        f"- **Source issue:** #{number}\n"
        f"- **Objective:** {objective}\n"
        "- **Status:** queued",
    )


def request(method: str, path: str, payload: dict | None = None) -> dict:
    if not REPOSITORY or not TOKEN:
        raise RuntimeError("GITHUB_REPOSITORY and GITHUB_TOKEN are required")
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        API + f"/repos/{REPOSITORY}{path}",
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {TOKEN}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "Genesis-Teammates/1.0",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            raw = response.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"GitHub API {exc.code} {method} {path}: {detail}") from exc


def comment(issue_number: int, body: str) -> None:
    request("POST", f"/issues/{issue_number}/comments", {"body": body})


def dispatch(workflow: str, inputs: dict[str, str]) -> None:
    request("POST", f"/actions/workflows/{workflow}/dispatches", {"ref": "main", "inputs": inputs})


ACTION_TOKENS = (
    "check", "fix", "solve", "do it", "investigate", "analyze", "analyse",
    "plan", "implement", "verify", "validate", "review", "research",
    "find", "compare", "test", "retry", "run", "deploy", "update",
    "change", "create", "close", "open", "why", "how", "what", "can ",
    "should ", "please", "?",
)

HARD_ADMIN_PREFIXES = (
    "### nexus is live",
    "nexus is live",
    "admin note:",
    "setup note:",
    "fyi:",
    "for information:",
)

STATUS_PREFIXES = (
    "status note:",
)

ADMIN_PHRASES = (
    "use this issue as the **only owner-facing ai team chat**",
    "use this issue as the only owner-facing ai team chat",
    "authority model:",
)


def source_already_processed(source_comment_id: str) -> bool:
    """Prevent duplicate routing when a workflow is retried or replayed."""
    nexus_issue = int(CONFIG["workspaces"]["nexus"])
    needle = f":{source_comment_id}"
    markers = (
        "<!-- genesis-nexus-routing:",
        "<!-- genesis-nexus-result:",
        "<!-- genesis-nexus-team-evolution:",
    )
    return any(
        needle in str(row.get("body") or "") and any(marker in str(row.get("body") or "") for marker in markers)
        for row in issue_comments(nexus_issue)
    )


def should_route_owner_comment(text: str) -> bool:
    """Return True only for owner comments that look like actionable requests.

    Explicit Genesis metadata/admin comments are always ignored. Informational
    notes are ignored unless they also contain a clear action/question token,
    preserving concise owner requests such as "Genesis is stuck" + "check it".
    """
    value = (text or "").strip()
    lower = value.lower()
    if not value:
        return False
    if "<!-- genesis-" in lower:
        return False
    if lower.startswith(HARD_ADMIN_PREFIXES):
        return False
    if any(phrase in lower for phrase in ADMIN_PHRASES):
        return False
    if lower.startswith(STATUS_PREFIXES):
        return any(token in lower for token in ACTION_TOKENS)
    return True


TEAM_EVOLUTION_ACTIONS = (
    "add teammate", "add agent", "new teammate", "new agent",
    "modify teammate", "modify agent", "change teammate", "change agent",
    "replace teammate", "replace agent", "disable teammate", "disable agent",
    "enable teammate", "enable agent", "remove teammate", "remove agent",
    "change role", "modify role", "new specialist",
)


def is_team_evolution_request(text: str) -> bool:
    value = (text or "").lower()
    return any(token in value for token in TEAM_EVOLUTION_ACTIONS)


def create_team_evolution_issue(objective: str, source_comment_id: str) -> int:
    title = f"[Nexus Team Evolution] {clean_title(objective)}"
    body = (
        "<!-- genesis-team-evolution -->\n"
        "**Authority:** Nexus may evolve specialist teammates when a capability gap or organizational need is identified.\n\n"
        f"**Nexus workspace:** #{CONFIG['workspaces']['nexus']}\n"
        f"**Source comment id:** {source_comment_id}\n\n"
        "## Requested evolution\n"
        f"{objective}\n\n"
        "## Required invariants\n"
        "- Genesis remains the Brain and identity authority.\n"
        "- Owner control and the Nexus-only owner entrypoint remain intact.\n"
        "- Every added specialist gets a permanent workspace issue and a separate workflow.\n"
        "- Modified specialists preserve an auditable issue history.\n"
        "- Removed/disabled specialists are retired without deleting historical comments.\n"
        "- Existing Agentic Lab, validation, safety, and promotion gates remain authoritative.\n"
        "- No teammate may self-approve a high-impact capability or bypass independent validation.\n"
    )
    result = request(
        "POST",
        "/issues",
        {"title": title, "body": body, "labels": ["genesis-autonomous", "agentic-lab"]},
    )
    return int(result["number"])


CASUAL_MESSAGES = {
    "hi", "hello", "hey", "hi nexus", "hello nexus", "hey nexus",
    "thanks", "thank you", "ok", "okay", "good morning",
    "good afternoon", "good evening",
}


def casual_response(text: str) -> str | None:
    value = re.sub(r"[^a-z0-9 ]+", "", (text or "").strip().lower())
    value = re.sub(r"\s+", " ", value).strip()
    if value not in CASUAL_MESSAGES:
        return None
    if value in {"thanks", "thank you"}:
        return "Acknowledged. The team is ready for the next request."
    if value in {"ok", "okay"}:
        return "Acknowledged."
    return "Nexus is available. Submit a request for analysis, planning, implementation, validation, research, or recovery."


ENGINEERING_ACTIONS = (
    "fix", "solve", "implement", "repair", "develop", "change code",
    "update code", "modify code", "workflow failure", "action failure",
)


def requires_engineering_pipeline(text: str) -> bool:
    value = (text or "").lower()
    return any(token in value for token in ENGINEERING_ACTIONS)


def next_handoff(agent: str, objective: str) -> str | None:
    """Return the next independent specialist for engineering work."""
    if not requires_engineering_pipeline(objective):
        return None
    if agent in {"atlas", "scout", "recovery"}:
        return "forge"
    if agent == "forge":
        return "sentinel"
    return None


def classify(text: str) -> str:
    value = text.lower()
    if any(k in value for k in ("stuck", "retry", "recovery", "keeps failing", "failed again", "exhausted", "blocked")):
        return "recovery"
    if any(k in value for k in ("review", "verify", "validate", "test", "qa", "regression")):
        return "sentinel"
    if any(k in value for k in ("architecture", "architect", "design", "plan", "structure", "workflow design", "dependency")):
        return "atlas"
    if any(k in value for k in ("research", "investigate", "find out", "compare", "evidence", "study", "analyze why")):
        return "scout"
    return "forge"


def provider_reason(agent: str, objective: str) -> tuple[str, str]:
    role, instruction = ROLE_MAP[agent]
    registry = ProviderRegistry()
    providers = registry.available_providers()
    preferred = [p for p in providers if getattr(p, "name", "") != "genesis-bootstrap"] or providers
    if not preferred:
        return "none", "No intelligence provider is currently available."
    provider = preferred[0]
    prompt = (
        f"ROLE: {role}\n"
        f"TEAMMATE: {agent}\n"
        f"INSTRUCTION: {instruction}\n"
        f"OBJECTIVE: {objective}\n"
        "Genesis is the Brain. Nexus is the team leader and only owner-facing teammate. "
        "Use neutral, professional, non-personified language. Avoid emotional, promotional, dramatic, or self-referential phrasing. "
        "Return concise findings, evidence, risks, and the smallest next action. "
        "If the current specialist roster lacks a capability needed to complete the objective safely, "
        "end with exactly: TEAM_CHANGE_REQUIRED: <specialist role>: <reason>. "
        "Do not claim execution that did not happen."
    )
    return provider.name, provider.reason(prompt)


def clean_title(text: str) -> str:
    compact = re.sub(r"\s+", " ", text).strip()
    return compact[:150] or "Owner request"


def create_execution_issue(agent: str, objective: str, source_comment_id: str) -> int:
    title = f"[Nexus Task][{agent.title()}] {clean_title(objective)}"
    body = (
        "<!-- genesis-team-task -->\n"
        f"**Requested by:** Nexus\n"
        f"**Specialist:** {agent}\n"
        f"**Nexus workspace:** #{CONFIG['workspaces']['nexus']}\n"
        f"**Source comment id:** {source_comment_id}\n\n"
        "## Objective\n"
        f"{objective}\n\n"
        "## Operating rule\n"
        "This is an internal execution issue created by the Genesis teammate system. "
        "Existing Agentic Lab, independent validation, safety, and closure authorities remain authoritative.\n"
    )
    labels = ["genesis-autonomous", "agentic-lab"]
    result = request("POST", "/issues", {"title": title, "body": body, "labels": labels})
    return int(result["number"])


def nexus(objective: str, actor: str, source_comment_id: str) -> None:
    nexus_issue = int(CONFIG["workspaces"]["nexus"])
    if not should_route_owner_comment(objective):
        return
    if source_already_processed(source_comment_id):
        return
    casual = casual_response(objective)
    if casual:
        comment(
            nexus_issue,
            f"<!-- genesis-nexus-result:{source_comment_id}:conversation -->\n"
            "### Nexus\n"
            f"{casual}",
        )
        return
    if is_team_evolution_request(objective):
        evolution_issue = create_team_evolution_issue(objective, source_comment_id)
        forge_issue = int(CONFIG["workspaces"]["forge"])
        comment(
            nexus_issue,
            f"<!-- genesis-nexus-team-evolution:{source_comment_id} -->\n"
            "### Nexus team evolution\n"
            f"- **Request:** {objective}\n"
            f"- **Evolution issue:** #{evolution_issue}\n"
            f"- **Implementation journal:** Forge #{forge_issue}\n"
            "- **Status:** admitted to the existing Agentic Lab/validation path\n\n"
            "Nexus is authorized to add, modify, disable, replace, or retire specialist teammates while preserving Genesis and owner-control invariants.",
        )
        comment(
            forge_issue,
            f"<!-- genesis-team-evolution-assignment:{source_comment_id} -->\n"
            "### Team evolution assignment from Nexus\n"
            f"- **Objective:** {objective}\n"
            f"- **Execution issue:** #{evolution_issue}\n"
            "- **Requirement:** maintain a separate permanent workspace issue and separate workflow for every active specialist.",
        )
        return
    agent = classify(objective)
    agent_issue = int(CONFIG["workspaces"][agent])
    workflow = str(CONFIG["workflows"][agent])
    marker = f"<!-- genesis-nexus-routing:{source_comment_id} -->"
    comment(
        nexus_issue,
        f"{marker}\n### Nexus routing\n"
        f"- **Request:** {objective}\n"
        f"- **Owner:** @{actor}\n"
        f"- **Assigned teammate:** **{agent.title()}** (workspace #{agent_issue})\n"
        "- **Status:** delegated\n\n"
        "Owner-facing updates remain in this workspace. Specialist activity is recorded in the assigned workspace and results are mirrored here.",
    )
    comment(
        agent_issue,
        f"<!-- genesis-team-assignment:{source_comment_id} -->\n"
        f"### Assignment from Nexus\n"
        f"- **Objective:** {objective}\n"
        f"- **Source:** Nexus #{nexus_issue}, comment {source_comment_id}\n"
        "- **Status:** queued",
    )
    dispatch(
        workflow,
        {
            "objective": objective[:10000],
            "source_comment_id": source_comment_id,
            "nexus_issue": str(nexus_issue),
        },
    )


def agent_run(
    agent: str,
    objective: str,
    source_comment_id: str,
    nexus_issue: int,
    source_issue: int | None = None,
) -> None:
    if source_issue is not None:
        try:
            source_issue = int(source_issue)
        except (TypeError, ValueError) as exc:
            raise RuntimeError("source issue must be a positive integer") from exc
        if source_issue <= 0:
            raise RuntimeError("source issue must be a positive integer")

    workspace = int(CONFIG["workspaces"][agent])
    if source_issue is not None:
        issue = request("GET", f"/issues/{source_issue}")
        if not is_autonomous_issue(issue):
            message = (
                f"<!-- genesis-team-autonomous-skip:{source_comment_id}:{agent} -->\n"
                f"Skipped source issue #{source_issue}: it is closed, not in the autonomous intake, "
                "or is held by an existing lifecycle gate."
            )
            comment(workspace, message)
            comment(nexus_issue, message)
            return

    comment(
        workspace,
        f"<!-- genesis-team-start:{source_comment_id}:{agent} -->\n"
        f"### {agent.title()} started\n"
        f"**Objective:** {objective}\n\n"
        "Processing the request under the Genesis/Nexus authority model.",
    )
    provider, output = provider_reason(agent, objective)
    execution_issue = None
    if agent in {"forge", "recovery"} and source_issue is None:
        execution_issue = create_execution_issue(agent, objective, source_comment_id)

    suffix = f"\n\n**Execution issue:** #{execution_issue}" if execution_issue else ""
    result_body = (
        f"<!-- genesis-team-result:{source_comment_id}:{agent} -->\n"
        f"### {agent.title()} result\n"
        f"- **Provider:** {provider}\n"
        f"- **Objective:** {objective}\n\n"
        f"{output}{suffix}"
    )
    comment(workspace, result_body)
    if source_issue is not None:
        comment(
            source_issue,
            f"<!-- genesis-team-source-result:{source_comment_id}:{agent} -->\n"
            f"### {agent.title()} autonomous findings\n\n"
            f"{output[:6000]}\n\n"
            "These findings are advisory. The existing issue owner and Genesis validation lifecycle remain authoritative.",
        )

    team_change_match = re.search(r"(?im)^TEAM_CHANGE_REQUIRED:\s*(.+)$", output)
    team_change_issue = None
    if team_change_match and CONFIG.get("rules", {}).get("nexus_can_evolve_team", False):
        requested = team_change_match.group(1).strip()
        team_change_issue = create_team_evolution_issue(
            f"Autonomous capability-gap request from {agent}: {requested}",
            source_comment_id,
        )
        comment(
            workspace,
            f"<!-- genesis-autonomous-team-evolution:{source_comment_id}:{agent} -->\n"
            f"Capability gap escalated to Nexus team evolution issue #{team_change_issue}.",
        )

    mirror = (
        f"<!-- genesis-nexus-result:{source_comment_id}:{agent} -->\n"
        f"### Nexus update — {agent.title()}\n"
        f"{output}{suffix}\n\n"
        f"Full specialist journal: #{workspace}"
        + (f"\n\nTeam evolution issue: #{team_change_issue}" if team_change_issue else "")
    )
    comment(nexus_issue, mirror)

    handoff = next_handoff(agent, objective)
    if handoff:
        next_workspace = int(CONFIG["workspaces"][handoff])
        next_workflow = str(CONFIG["workflows"][handoff])
        comment(
            workspace,
            f"<!-- genesis-team-handoff:{source_comment_id}:{agent}:{handoff} -->\n"
            f"### Handoff to {handoff.title()}\n"
            f"- **Objective:** {objective}\n"
            f"- **From:** {agent.title()}\n"
            f"- **To:** {handoff.title()} (workspace #{next_workspace})\n"
            "- **Rule:** use the prior specialist result as context, but verify repository evidence independently.",
        )
        comment(
            next_workspace,
            f"<!-- genesis-team-assignment:{source_comment_id}:{handoff} -->\n"
            f"### Handoff assignment from {agent.title()}\n"
            f"- **Objective:** {objective}\n"
            f"- **Source workspace:** #{workspace}\n"
            "- **Status:** queued",
        )
        handoff_inputs = {
            "objective": objective[:10000],
            "source_comment_id": source_comment_id,
            "nexus_issue": str(nexus_issue),
        }
        if source_issue is not None:
            handoff_inputs["source_issue"] = str(source_issue)
        dispatch(next_workflow, handoff_inputs)


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)

    n = sub.add_parser("nexus")
    n.add_argument("--objective", required=True)
    n.add_argument("--actor", required=True)
    n.add_argument("--source-comment-id", required=True)

    auto = sub.add_parser("autonomous")
    auto.add_argument("--run-id", required=True)

    a = sub.add_parser("agent")
    a.add_argument("--agent", required=True, choices=tuple(ROLE_MAP))
    a.add_argument("--objective", required=True)
    a.add_argument("--source-comment-id", required=True)
    a.add_argument("--nexus-issue", required=True, type=int)
    a.add_argument("--source-issue", type=int)

    args = parser.parse_args()
    if args.command == "nexus":
        nexus(args.objective, args.actor, args.source_comment_id)
    elif args.command == "autonomous":
        autonomous_development(args.run_id)
    else:
        agent_run(args.agent, args.objective, args.source_comment_id, args.nexus_issue, args.source_issue)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
