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

ROLE_MAP = {
    "atlas": ("planner", "Architecture and decomposition. Produce a bounded design, dependencies, risks, and handoff."),
    "forge": ("engineer", "Implementation and repair. Produce the smallest safe implementation path and execution acceptance criteria."),
    "sentinel": ("validator", "Independent QA and validation. Define pass/fail evidence and reject unsupported completion claims."),
    "scout": ("researcher", "Research and investigation. Gather repository evidence, unknowns, and the next evidence-producing action."),
    "recovery": ("reviewer", "Recovery and troubleshooting. Identify why prior attempts failed and require a materially different next strategy."),
}


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

ADMIN_PREFIXES = (
    "### nexus is live",
    "nexus is live",
    "status note:",
    "admin note:",
    "setup note:",
    "fyi:",
    "for information:",
)

ADMIN_PHRASES = (
    "use this issue as the **only owner-facing ai team chat**",
    "use this issue as the only owner-facing ai team chat",
    "authority model:",
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
    if lower.startswith(ADMIN_PREFIXES):
        return any(token in lower for token in ACTION_TOKENS)
    if any(phrase in lower for phrase in ADMIN_PHRASES):
        return any(token in lower for token in ACTION_TOKENS)
    return True


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
        "Return concise findings, evidence, risks, and the smallest next action. "
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
        "I will keep the owner-facing conversation here. Specialist activity is recorded in its own workspace and results are mirrored back to Nexus.",
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


def agent_run(agent: str, objective: str, source_comment_id: str, nexus_issue: int) -> None:
    workspace = int(CONFIG["workspaces"][agent])
    comment(
        workspace,
        f"<!-- genesis-team-start:{source_comment_id}:{agent} -->\n"
        f"### {agent.title()} started\n"
        f"**Objective:** {objective}\n\n"
        "Reading the current request under Genesis/Nexus authority.",
    )
    provider, output = provider_reason(agent, objective)
    execution_issue = None
    if agent in {"forge", "recovery"}:
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

    mirror = (
        f"<!-- genesis-nexus-result:{source_comment_id}:{agent} -->\n"
        f"### Nexus update — {agent.title()}\n"
        f"{output}{suffix}\n\n"
        f"Full specialist journal: #{workspace}"
    )
    comment(nexus_issue, mirror)


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)

    n = sub.add_parser("nexus")
    n.add_argument("--objective", required=True)
    n.add_argument("--actor", required=True)
    n.add_argument("--source-comment-id", required=True)

    a = sub.add_parser("agent")
    a.add_argument("--agent", required=True, choices=tuple(ROLE_MAP))
    a.add_argument("--objective", required=True)
    a.add_argument("--source-comment-id", required=True)
    a.add_argument("--nexus-issue", required=True, type=int)

    args = parser.parse_args()
    if args.command == "nexus":
        nexus(args.objective, args.actor, args.source_comment_id)
    else:
        agent_run(args.agent, args.objective, args.source_comment_id, args.nexus_issue)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
