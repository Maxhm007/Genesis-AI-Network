from __future__ import annotations

from pathlib import Path

from .github_issue_task_router import issue_authority_enabled
from .github_issue_terminal_reconciler import GithubRequester, _github_request, _protected_issue
from .modules.task_queue import GenesisTask


EVIDENCE_MARKER_PREFIX = "genesis-specialist-completion"


def _issue_number(task: GenesisTask) -> int:
    try:
        return int(task.payload.get("github_issue_number") or 0)
    except (TypeError, ValueError):
        return 0


def _evidence_body(task: GenesisTask, review_path: Path, team_members: list[str]) -> str:
    try:
        artifact = review_path.resolve().relative_to(review_path.resolve().parents[2]).as_posix()
    except (ValueError, IndexError):
        artifact = review_path.name
    members = ", ".join(sorted({str(member).strip() for member in team_members if str(member).strip()})) or "recorded in artifact"
    task_type = str(task.payload.get("task_type") or "specialist_task")
    return (
        f"<!-- {EVIDENCE_MARKER_PREFIX}:{task.task_id} -->\n"
        "Genesis specialist execution produced its bounded review artifact.\n\n"
        f"- Task ID: `{task.task_id}`\n"
        f"- Task type: `{task_type}`\n"
        f"- Review artifact: `{artifact}`\n"
        f"- Specialist team: {members}\n\n"
        "This is candidate/review evidence only. It does not self-award a benchmark score, "
        "promote an unvalidated scientific claim, or bypass code/security/promotion controls."
    )


def publish_specialist_completion_evidence(
    root: Path,
    task: GenesisTask,
    *,
    review_path: Path,
    team_members: list[str],
    requester: GithubRequester | None = None,
) -> dict:
    """Publish bounded specialist evidence before an Issue-backed task becomes terminal.

    The caller must keep the task in ``review`` until this succeeds. That ordering
    prevents the generic terminal reconciler from closing the authoritative Issue
    without the specialist evidence being attached first.
    """
    root = Path(root).resolve()
    review_path = Path(review_path).resolve()
    explicit_requester = requester is not None
    enforced = bool(explicit_requester or issue_authority_enabled(root))
    issue_number = _issue_number(task)
    result = {
        "status": "not_applicable",
        "reported": False,
        "github_issue_number": issue_number,
        "task_id": task.task_id,
        "enforced": enforced,
    }

    if not enforced:
        result["reason"] = "github_issue_authority_disabled"
        return result
    if issue_number <= 0:
        result["status"] = "blocked"
        result["reason"] = "missing_github_issue_number"
        return result
    if task.state != "review":
        result["status"] = "blocked"
        result["reason"] = f"task_not_in_review:{task.state}"
        return result
    if not review_path.is_file():
        result["status"] = "blocked"
        result["reason"] = "review_artifact_missing"
        return result

    requester = requester or _github_request
    issue = requester("GET", f"/issues/{issue_number}", None)
    if not isinstance(issue, dict):
        result["status"] = "blocked"
        result["reason"] = "github_issue_unavailable"
        return result
    if str(issue.get("state") or "open") == "closed":
        result["status"] = "blocked"
        result["reason"] = "github_issue_already_closed_before_specialist_completion"
        return result
    if _protected_issue(issue):
        result["status"] = "blocked"
        result["reason"] = "protected_github_issue"
        return result

    marker = f"<!-- {EVIDENCE_MARKER_PREFIX}:{task.task_id} -->"
    comments = requester("GET", f"/issues/{issue_number}/comments?per_page=100", None)
    if isinstance(comments, list):
        for comment in comments:
            if marker in str((comment or {}).get("body") or ""):
                result["status"] = "already_reported"
                result["reported"] = True
                return result

    body = _evidence_body(task, review_path, team_members)
    posted = requester("POST", f"/issues/{issue_number}/comments", {"body": body})
    if not isinstance(posted, dict):
        result["status"] = "blocked"
        result["reason"] = "github_completion_evidence_comment_failed"
        return result

    result["status"] = "reported"
    result["reported"] = True
    return result
