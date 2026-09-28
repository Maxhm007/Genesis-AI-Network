from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable

GithubRequester = Callable[[str, str, dict | None], object | None]
LINKED_ISSUE_RE = re.compile(r"(?i)\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\s+#(\d+)\b")
SUPERSEDED_RE = re.compile(r"(?i)\b(?:superseded|obsolete|replaced by)\b")


@dataclass(frozen=True)
class PullRequestAssessment:
    number: int
    classification: str
    linked_issues: tuple[int, ...]
    reasons: tuple[str, ...]


def _number(value: object) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def linked_issue_numbers(pr: dict) -> tuple[int, ...]:
    text = f"{pr.get('title') or ''}\n{pr.get('body') or ''}"
    return tuple(sorted({_number(match) for match in LINKED_ISSUE_RE.findall(text) if _number(match) > 0}))


def _checks_pass(checks: object) -> bool:
    if not isinstance(checks, list) or not checks:
        return False
    conclusions = {str(row.get("conclusion") or "").lower() for row in checks if isinstance(row, dict)}
    return bool(conclusions) and conclusions <= {"success", "neutral", "skipped"}


def _approved(reviews: object) -> bool:
    if not isinstance(reviews, list):
        return False
    latest: dict[str, str] = {}
    for review in reviews:
        if not isinstance(review, dict):
            continue
        user = review.get("user") or {}
        login = str(user.get("login") or "") if isinstance(user, dict) else ""
        state = str(review.get("state") or "").upper()
        if login:
            latest[login] = state
    return any(state == "APPROVED" for state in latest.values())


def classify_pull_request(
    pr: dict,
    *,
    checks: object = None,
    reviews: object = None,
    superseded: bool = False,
) -> PullRequestAssessment:
    number = _number(pr.get("number"))
    linked = linked_issue_numbers(pr)
    reasons: list[str] = []
    if superseded or SUPERSEDED_RE.search(str(pr.get("body") or "")):
        return PullRequestAssessment(number, "superseded", linked, ("explicit_supersession_evidence",))
    if bool(pr.get("draft")):
        return PullRequestAssessment(number, "needs-review", linked, ("draft",))
    mergeable = pr.get("mergeable")
    mergeable_state = str(pr.get("mergeable_state") or "").lower()
    if mergeable is False or mergeable_state in {"dirty", "behind"}:
        return PullRequestAssessment(number, "needs-refresh", linked, ("merge_conflict_or_stale_base",))
    if not _checks_pass(checks):
        reasons.append("required_validation_not_green")
    if not _approved(reviews):
        reasons.append("approval_missing")
    if reasons:
        return PullRequestAssessment(number, "blocked", linked, tuple(reasons))
    return PullRequestAssessment(number, "merge-ready", linked, ("validation_and_review_passed",))


def _list_open_prs(requester: GithubRequester) -> list[dict] | None:
    rows: list[dict] = []
    for page in range(1, 101):
        response = requester("GET", f"/pulls?state=open&per_page=100&page={page}", None)
        if not isinstance(response, list):
            return None
        rows.extend(dict(row) for row in response if isinstance(row, dict))
        if len(response) < 100:
            break
    return rows


def maintain_open_pull_requests(
    requester: GithubRequester,
    *,
    allow_merge: bool = True,
    allow_close_superseded: bool = True,
) -> dict:
    """Bounded PR maintenance preserving branch protection and Issue authority.

    This lane never acts because of age alone. A merge requires GitHub to report the
    PR mergeable, all returned checks green/neutral/skipped, and at least one current
    approval. Supersession requires explicit evidence. Closing a superseded PR requeues
    linked open Issues instead of treating PR closure as Issue completion.
    """
    prs = _list_open_prs(requester)
    result = {"status": "ok", "scanned": 0, "assessments": [], "merged": [], "closed": [], "requeued": [], "blocked": []}
    if prs is None:
        result["status"] = "blocked"
        result["blocked"].append({"reason": "github_open_pr_list_unavailable"})
        return result
    result["scanned"] = len(prs)

    for pr in sorted(prs, key=lambda row: _number(row.get("number"))):
        number = _number(pr.get("number"))
        if number <= 0:
            continue
        checks = requester("GET", f"/commits/{pr.get('head', {}).get('sha', '')}/check-runs?per_page=100", None)
        check_rows = checks.get("check_runs") if isinstance(checks, dict) else None
        reviews = requester("GET", f"/pulls/{number}/reviews?per_page=100", None)
        assessment = classify_pull_request(pr, checks=check_rows, reviews=reviews)
        result["assessments"].append({
            "number": number,
            "classification": assessment.classification,
            "linked_issues": list(assessment.linked_issues),
            "reasons": list(assessment.reasons),
        })

        if assessment.classification == "merge-ready" and allow_merge:
            merged = requester("PUT", f"/pulls/{number}/merge", {"merge_method": "squash"})
            if isinstance(merged, dict) and bool(merged.get("merged")):
                result["merged"].append(number)
            else:
                result["blocked"].append({"number": number, "reason": "protected_merge_rejected"})
            continue

        if assessment.classification == "superseded" and allow_close_superseded:
            comment = (
                "Genesis PR Maintenance: closing this PR because explicit supersession/obsolescence "
                "evidence is present. Age alone was not used. Linked unresolved Issues remain authoritative "
                "and are requeued for the normal solve→verify→promote→close lifecycle."
            )
            requester("POST", f"/issues/{number}/comments", {"body": comment})
            closed = requester("PATCH", f"/pulls/{number}", {"state": "closed"})
            if not isinstance(closed, dict) or str(closed.get("state") or "") != "closed":
                result["blocked"].append({"number": number, "reason": "superseded_close_failed"})
                continue
            result["closed"].append(number)
            for issue_number in assessment.linked_issues:
                issue = requester("GET", f"/issues/{issue_number}", None)
                if not isinstance(issue, dict) or str(issue.get("state") or "") != "open":
                    continue
                labels = issue.get("labels") or []
                names = [str(x.get("name") or "") if isinstance(x, dict) else str(x) for x in labels]
                if "genesis-autonomous" not in names:
                    names.append("genesis-autonomous")
                updated = requester("PATCH", f"/issues/{issue_number}", {"labels": names})
                if isinstance(updated, dict):
                    result["requeued"].append(issue_number)

    if result["blocked"]:
        result["status"] = "partial" if result["assessments"] else "blocked"
    return result
