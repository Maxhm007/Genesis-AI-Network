from __future__ import annotations

import argparse
import json
import os
import re
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

from genesis.providers import ProviderRegistry

ROOT = Path(__file__).resolve().parents[1]
CONFIG = json.loads((ROOT / "config" / "genesis_teammates.json").read_text(encoding="utf-8"))
REPOSITORY = os.environ.get("GITHUB_REPOSITORY", "").strip()
TOKEN = os.environ.get("GITHUB_TOKEN", "").strip() or os.environ.get("GH_TOKEN", "").strip()
API = "https://api.github.com"

TEAM_TASK_SOURCE_RE = re.compile(r"Autonomous Genesis development task from issue #(\\d+):", re.IGNORECASE)

CURRENT_PROBLEM_MARKER = "<!-- genesis-team-current-problem -->"
PROBLEM_HINTS = (
    "repair status:", "provider_timeout", "provider_error", "malformed json",
    "failed", "failure", "error", "stuck", "blocked", "exhausted",
    "retry_pending", "not produce a verified promotion",
)

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


def latest_problem_comment(comments: list[dict], fallback: str = "") -> str:
    """Return the newest comment that describes the present unresolved problem."""
    for row in reversed(comments):
        body = str(row.get("body") or "").strip()
        lower = body.lower()
        if not body:
            continue
        if "<!-- genesis-closure-certificate -->" in lower:
            continue
        if "genesis verification evidence:" in lower or "verified and promoted" in lower:
            continue
        if any(token in lower for token in PROBLEM_HINTS):
            return body[:3500]
    return str(fallback or "").strip()[:3500]


def current_problem_context(issue: dict) -> str:
    number = int(issue.get("number") or 0)
    title = str(issue.get("title") or "")
    body = str(issue.get("body") or "")
    latest = latest_problem_comment(issue_comments(number), fallback=body)
    return (
        f"Current authoritative problem for issue #{number} ({title}):\n"
        f"{latest}\n\n"
        "Rule: solve the newest current problem first. If an attempt fails or the problem changes, "
        "append a new issue comment describing the exact present failure before retrying."
    )


def reconcile_legacy_team_tasks() -> list[int]:
    """Retire old Nexus execution issues that duplicate an authoritative source issue."""
    protected = set(int(v) for v in CONFIG.get("workspaces", {}).values())
    retired: list[int] = []
    for issue in paged_get("/issues?state=open"):
        number = int(issue.get("number") or 0)
        if number <= 0 or number in protected or issue.get("pull_request"):
            continue
        body = str(issue.get("body") or "")
        if "<!-- genesis-team-task -->" not in body:
            continue
        match = TEAM_TASK_SOURCE_RE.search(body)
        if not match:
            continue
        source_number = int(match.group(1))
        if source_number == number:
            continue
        try:
            source = request("GET", f"/issues/{source_number}")
        except RuntimeError:
            continue
        if not isinstance(source, dict) or source.get("pull_request"):
            continue
        labels = {
            str(row.get("name") or "") if isinstance(row, dict) else str(row or "")
            for row in (issue.get("labels") or [])
        }
        if "genesis-superseded" not in labels:
            request("POST", f"/issues/{number}/labels", {"labels": ["genesis-superseded"]})
            comment(
                number,
                "<!-- genesis-team-duplicate-retired -->\n"
                f"Nexus retired this legacy execution record because authoritative source issue #{source_number} owns the work. "
                "Closure Manager should close this duplicate automatically.",
            )
        retired.append(number)
    return retired


def open_development_issues() -> list[dict]:
    protected = set(int(v) for v in CONFIG.get("workspaces", {}).values())
    rows = paged_get("/issues?state=open")
    out: list[dict] = []
    for issue in rows:
        number = int(issue.get("number") or 0)
        if number in protected:
            continue
        if issue.get("pull_request"):
            continue
        title = str(issue.get("title") or "")
        body = str(issue.get("body") or "")
        if "<!-- genesis-team-task -->" in body and TEAM_TASK_SOURCE_RE.search(body):
            # Legacy duplicate execution records are retired by
            # reconcile_legacy_team_tasks(); work continues on the source issue.
            continue
        if title.startswith("[Genesis Teammate]"):
            continue
        out.append(issue)
    return out


def autonomous_claim_exists(issue_number: int) -> bool:
    """Treat only a recent team claim as active.

    Older claims must not permanently blacklist an open issue. If an autonomous
    attempt stalls, the team may reclaim it after the cooldown and try again.
    """
    marker = f"<!-- genesis-team-autonomous-claim:{issue_number} -->"
    cutoff = datetime.now(timezone.utc) - timedelta(hours=2)
    for row in reversed(issue_comments(issue_number)):
        if marker not in str(row.get("body") or ""):
            continue
        created = str(row.get("created_at") or "").strip()
        if not created:
            return False
        try:
            claimed_at = datetime.fromisoformat(created.replace("Z", "+00:00"))
        except ValueError:
            return False
        return claimed_at >= cutoff
    return False


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
        if labels & {
            "genesis-owner-paused",
            "genesis-verified", "genesis-waiting-capability", "genesis-needs-human",
            "genesis-working", "genesis-verifying", "genesis-repair-in-progress",
            "genesis-validating", "genesis-claimed", "genesis-deepseek-working",
            "genesis-deepseek-handoff-pending",
        }:
            continue
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
    retired = reconcile_legacy_team_tasks()
    if retired:
        comment(
            nexus_issue,
            f"<!-- genesis-team-backlog-reconcile:{run_id} -->\n"
            "### Autonomous backlog reconciliation\n"
            f"Retired duplicate legacy execution issues: {', '.join('#' + str(n) for n in retired)}. "
            "Authoritative source issues remain assigned to the team.",
        )
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
    current_problem = current_problem_context(issue)
    objective = (
        f"Autonomous Genesis development task from issue #{number}: {title}.\n\n"
        f"{current_problem}\n\n"
        + (f"Original issue context: {body[:2500]}" if body else "")
    ).strip()
    # Acceptance criteria often mention tests/reviews regardless of the task's
    # actual role. Route by the requested work, not incidental body keywords.
    agent = classify(title)
    workspace = int(CONFIG["workspaces"][agent])
    workflow = str(CONFIG["workflows"][agent])
    marker = f"<!-- genesis-team-autonomous-claim:{number} -->"

    comment(
        number,
        f"{CURRENT_PROBLEM_MARKER}\n"
        "### Current problem selected by Nexus\n"
        f"{current_problem}\n\n"
        "This comment is the active problem statement for the current team attempt. "
        "Later failure comments supersede it.",
    )

    comment(
        nexus_issue,
        f"<!-- genesis-team-autonomous-route:{run_id}:{number} -->\n"
        "### Autonomous Genesis development\n"
        f"- **Source issue:** #{number} — {title}\n"
        f"- **Assigned teammate:** {agent.title()} (workspace #{workspace})\n"
        "- **Status:** preparing delegation without owner prompt",
    )
    comment(
        workspace,
        f"<!-- genesis-team-autonomous-assignment:{number} -->\n"
        "### Autonomous assignment from Nexus\n"
        f"- **Source issue:** #{number}\n"
        f"- **Objective:** {objective}\n"
        "- **Status:** queued",
    )
    dispatch(
        workflow,
        {
            "objective": objective[:10000],
            "source_comment_id": f"autonomous-{number}-{run_id}",
            "nexus_issue": str(nexus_issue),
        },
    )
    comment(
        number,
        f"{marker}\n"
        f"### Nexus autonomous team claim\n"
        f"- **Assigned teammate:** {agent.title()} (workspace #{workspace})\n"
        f"- **Nexus:** #{nexus_issue}\n"
        "- **Status:** workflow dispatched\n"
        "- **Rule:** existing Agentic Lab, validation, and issue-closure authorities remain authoritative.",
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


def wake_agentic_lab() -> None:
    """Wake the authoritative execution pipeline after teammate task creation."""
    request(
        "POST",
        "/actions/workflows/genesis-agentic-lab-recovery.yml/dispatches",
        {"ref": "main"},
    )


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
    markers = (
        "<!-- genesis-nexus-dispatched:",
        "<!-- genesis-nexus-result:",
        "<!-- genesis-nexus-team-evolution:",
    )
    return any(
        re.search(
            re.escape(marker + source_comment_id) + r"(?::| -->)",
            str(row.get("body") or ""),
        )
        for row in issue_comments(nexus_issue)
        for marker in markers
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
    return any(token in value for token in TEAM_EVOLUTION_ACTIONS) or bool(
        re.search(r"\b(?:add|new|modify|change|replace|disable|enable|remove)\b[^\n.!?]{0,60}\b(?:teammate|agent|specialist)\b", value)
    )


def create_team_evolution_issue(objective: str, source_comment_id: str) -> int:
    source = f"**Source comment id:** {source_comment_id}"
    for issue in paged_get("/issues?state=open"):
        body = str(issue.get("body") or "")
        if "<!-- genesis-team-evolution -->" in body and source in body.splitlines():
            return int(issue["number"])
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


def execution_task_key(objective: str, source_comment_id: str) -> str:
    """Return a stable key so one objective maps to one execution issue."""
    match = re.search(r"(?i)autonomous genesis development task from issue #(\d+)", objective or "")
    if match:
        return f"source-issue-{match.group(1)}"
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "-", str(source_comment_id or "").strip()).strip("-")
    return f"source-comment-{safe or 'unknown'}"


def find_open_execution_issue(task_key: str) -> int | None:
    marker = f"<!-- genesis-team-task-key:{task_key} -->"
    for issue in paged_get("/issues?state=open"):
        body = str(issue.get("body") or "")
        if "<!-- genesis-team-task -->" in body and marker in body:
            return int(issue.get("number") or 0) or None
    # Legacy compatibility: older teammate tasks do not have task-key markers.
    if task_key.startswith("source-issue-"):
        source_number = task_key.removeprefix("source-issue-")
        needle = f"Autonomous Genesis development task from issue #{source_number}:"
        for issue in paged_get("/issues?state=open"):
            body = str(issue.get("body") or "")
            if "<!-- genesis-team-task -->" in body and needle in body:
                return int(issue.get("number") or 0) or None
    return None


def create_execution_issue(agent: str, objective: str, source_comment_id: str) -> int:
    # Autonomous specialists work on the existing authoritative issue. Creating
    # another Nexus task here duplicated the backlog without advancing it.
    source = re.fullmatch(r"autonomous-(\d+)-.+", source_comment_id)
    if source:
        number = int(source.group(1))
        issue = request("GET", f"/issues/{number}")
        if issue.get("pull_request") or number in CONFIG["workspaces"].values():
            raise RuntimeError("Autonomous execution requires a task issue")
        if str(issue.get("state") or "").lower() != "open":
            raise RuntimeError("Autonomous source issue is no longer open")
        labels = {str(row.get("name") or "") for row in issue.get("labels") or []}
        if not {"genesis-autonomous", "agentic-lab"} <= labels:
            request("POST", f"/issues/{number}/labels", {
                "labels": ["genesis-autonomous", "agentic-lab"],
            })
        return number
    task_key = execution_task_key(objective, source_comment_id)
    existing = find_open_execution_issue(task_key)
    if existing:
        comment(
            existing,
            f"<!-- genesis-team-task-reuse:{source_comment_id}:{agent} -->\n"
            f"Nexus reused this execution issue for **{agent.title()}** because task key `{task_key}` is already active.",
        )
        return existing

    title = f"[Nexus Task] {clean_title(objective)}"
    body = (
        "<!-- genesis-team-task -->\n"
        f"<!-- genesis-team-task-key:{task_key} -->\n"
        f"**Requested by:** Nexus\n"
        f"**Initial specialist:** {agent}\n"
        f"**Nexus workspace:** #{CONFIG['workspaces']['nexus']}\n"
        f"**Source comment id:** {source_comment_id}\n\n"
        "## Objective\n"
        f"{objective}\n\n"
        "## Operating rule\n"
        "This is the single internal execution issue for this objective. "
        "Recovery, Forge, Sentinel, and other specialists must reuse this issue rather than create parallel copies. "
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
        wake_agentic_lab()
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
        "- **Status:** preparing delegation\n\n"
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
    comment(
        nexus_issue,
        f"<!-- genesis-nexus-dispatched:{source_comment_id} -->\n"
        f"Nexus dispatched {agent.title()}'s workflow for this request.",
    )


def agent_run(agent: str, objective: str, source_comment_id: str, nexus_issue: int) -> None:
    workspace = int(CONFIG["workspaces"][agent])
    comment(
        workspace,
        f"<!-- genesis-team-start:{source_comment_id}:{agent} -->\n"
        f"### {agent.title()} started\n"
        f"**Objective:** {objective}\n\n"
        "Processing the request under the Genesis/Nexus authority model.",
    )
    provider, output = provider_reason(agent, objective)
    execution_issue = None
    if agent in {"forge", "recovery"}:
        execution_issue = create_execution_issue(agent, objective, source_comment_id)
        # Teammates are planners/coordinators; Agentic Lab is the authoritative
        # repository executor. Wake it immediately so the execution issue is
        # not left as a passive comment-only handoff.
        if execution_issue:
            comment(
                execution_issue,
                f"{CURRENT_PROBLEM_MARKER}\n"
                f"### {agent.title()} current problem\n"
                f"{latest_problem_comment(issue_comments(execution_issue), fallback=objective)}\n\n"
                "If this attempt fails, record the exact new failure on this same issue before the next retry.",
            )
        wake_agentic_lab()

    suffix = f"\n\n**Execution issue:** #{execution_issue}" if execution_issue else ""
    result_body = (
        f"<!-- genesis-team-result:{source_comment_id}:{agent} -->\n"
        f"### {agent.title()} result\n"
        f"- **Provider:** {provider}\n"
        f"- **Objective:** {objective}\n\n"
        f"{output}{suffix}"
    )
    comment(workspace, result_body)

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
        dispatch(
            next_workflow,
            {
                "objective": objective[:10000],
                "source_comment_id": source_comment_id,
                "nexus_issue": str(nexus_issue),
            },
        )


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

    args = parser.parse_args()
    if args.command == "nexus":
        nexus(args.objective, args.actor, args.source_comment_id)
    elif args.command == "autonomous":
        autonomous_development(args.run_id)
    else:
        agent_run(args.agent, args.objective, args.source_comment_id, args.nexus_issue)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
